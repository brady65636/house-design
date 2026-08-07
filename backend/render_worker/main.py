"""无头渲染 worker:为 render-bridge 保持一个浏览器渲染会话在线。

架构:浏览器页面里的 renderBridgeWorker.ts(Web Worker)负责心跳、拉命令、
执行渲染、回传结果;本进程只负责启动浏览器、保持页面存活、崩溃重启与日志,
不重写轮询逻辑。

env:
- VIEWER_URL:viewer 生产页面地址(通常为已部署的 Vercel 域名)
- RENDER_SESSION_ID:注册到 render-bridge 的会话名(生产默认 worker,
  独立于交互页 local-demo,避免多标签页抢命令的已知问题)
- RENDER_BRIDGE_URL:render-bridge 地址
- AGENT_API_URL:agent-api 地址(页面用 ?agent_api= 从 /api/scheme 拉方案)
- HEALTH_INTERVAL_SECONDS:探活间隔(默认 15)
- ONLINE_TIMEOUT_SECONDS:session 上线等待上限(默认 120)

运行方式:python -m backend.render_worker.main
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time

import httpx
from playwright.sync_api import sync_playwright

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [render_worker] %(message)s",
)
logger = logging.getLogger("render_worker")

VIEWER_URL = os.environ.get("VIEWER_URL", "").rstrip("/")
RENDER_SESSION_ID = os.environ.get("RENDER_SESSION_ID", "worker")
RENDER_BRIDGE_URL = os.environ.get("RENDER_BRIDGE_URL", "http://127.0.0.1:8765").rstrip("/")
AGENT_API_URL = os.environ.get("AGENT_API_URL", "").rstrip("/")
HEALTH_INTERVAL = float(os.environ.get("HEALTH_INTERVAL_SECONDS", "15"))
ONLINE_TIMEOUT = float(os.environ.get("ONLINE_TIMEOUT_SECONDS", "120"))

CHROMIUM_ARGS = [
    "--headless=new",
    "--use-angle=swiftshader",  # 软件渲染:无 GPU 环境下的 WebGL
    "--disable-gpu",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]


class RenderWorker:
    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._page = None
        self._stopping = False

    def _target_url(self) -> str:
        query = [
            f"render_session={RENDER_SESSION_ID}",
            f"render_bridge={RENDER_BRIDGE_URL}",
        ]
        if AGENT_API_URL:
            query.append(f"agent_api={AGENT_API_URL}")
        return f"{VIEWER_URL}/?{'&'.join(query)}"

    def _session_online(self) -> bool:
        try:
            response = httpx.get(
                f"{RENDER_BRIDGE_URL}/v1/render-sessions/{RENDER_SESSION_ID}/status",
                timeout=3,
                trust_env=False,
            )
            return response.status_code == 200 and response.json().get("online") is True
        except (httpx.HTTPError, ValueError):
            return False

    def _page_alive(self) -> bool:
        try:
            return self._page is not None and not self._page.is_closed()
        except Exception:  # noqa: BLE001
            return False

    def start(self) -> None:
        """启动浏览器并打开 worker 页面,等 render session 上线。"""
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=True,
            args=CHROMIUM_ARGS,
        )
        url = self._target_url()
        logger.info("opening %s", url)
        self._page = self._browser.new_page()
        self._page.goto(url, wait_until="networkidle", timeout=120_000)
        logger.info("page loaded; waiting for render session %s", RENDER_SESSION_ID)

        deadline = time.monotonic() + ONLINE_TIMEOUT
        while time.monotonic() < deadline and not self._stopping:
            if self._page_alive() and self._session_online():
                logger.info("render session online")
                return
            time.sleep(2)
        raise RuntimeError(
            f"render session {RENDER_SESSION_ID} did not come online within {ONLINE_TIMEOUT:.0f}s"
        )

    def supervise(self) -> None:
        """主监督循环:页面/会话掉线则重启浏览器(带退避),直到收到停止信号。"""
        restart_backoff = 10
        while not self._stopping:
            try:
                self.start()
                restart_backoff = 10
            except Exception as error:  # noqa: BLE001
                logger.warning("worker start failed: %s", error)
                self.cleanup()
                self._sleep(restart_backoff)
                restart_backoff = min(restart_backoff * 2, 120)
                continue

            while not self._stopping:
                self._sleep(HEALTH_INTERVAL)
                if not self._page_alive():
                    logger.warning("render page died; restarting")
                    break
                if not self._session_online():
                    logger.warning("render session went offline; restarting")
                    break
            self.cleanup()

        logger.info("worker stopping")
        self.cleanup()

    def _sleep(self, seconds: float) -> None:
        """可中断的 sleep:收到停止信号立即退出。"""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and not self._stopping:
            time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))

    def cleanup(self) -> None:
        try:
            if self._page is not None:
                self._page.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._playwright is not None:
                self._playwright.stop()
        except Exception:  # noqa: BLE001
            pass
        self._page = None
        self._browser = None
        self._playwright = None


def main() -> None:
    if not VIEWER_URL:
        logger.error("VIEWER_URL 未设置;无法打开渲染页面")
        sys.exit(1)

    worker = RenderWorker()

    def _handle_signal(_signum, _frame) -> None:
        logger.info("received shutdown signal; stopping")
        worker._stopping = True

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        worker.supervise()
    finally:
        worker.cleanup()


if __name__ == "__main__":
    main()

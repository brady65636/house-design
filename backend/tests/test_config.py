"""LLM 配置隔离测试：全局供应商变量不能污染本项目。"""

import os
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from backend.agent_api.config import Settings


class LlmConfigurationIsolationTests(unittest.TestCase):
    def test_generic_openai_environment_is_ignored(self) -> None:
        polluted_environment = {
            "OPENAI_API_KEY": "sk-deepseek-mislabelled-as-openai",
            "OPENAI_BASE_URL": "https://api.deepseek.com/v1",
            "OPENAI_MODEL": "deepseek-chat",
            "DEEPSEEK_API_KEY": "sk-deepseek",
        }
        with patch.dict(os.environ, polluted_environment, clear=True):
            isolated = Settings(_env_file=None)

        self.assertEqual(isolated.openai_api_key, "")
        self.assertEqual(isolated.openai_base_url, "https://api.openai.com/v1")
        self.assertEqual(isolated.openai_model, "gpt-5.6-luna")

    def test_project_namespace_wins_in_polluted_environment(self) -> None:
        environment = {
            "OPENAI_API_KEY": "sk-wrong-global-key",
            "OPENAI_BASE_URL": "https://api.deepseek.com/v1",
            "OPENAI_MODEL": "deepseek-chat",
            "HOUSE_DESIGN_LLM_PROVIDER": "openai",
            "HOUSE_DESIGN_OPENAI_API_KEY": "sk-project-openai-key-1234",
            "HOUSE_DESIGN_OPENAI_BASE_URL": "https://api.openai.com/v1/",
            "HOUSE_DESIGN_OPENAI_MODEL": "project-model",
        }
        with patch.dict(os.environ, environment, clear=True):
            isolated = Settings(_env_file=None)

        self.assertEqual(isolated.openai_api_key, "sk-project-openai-key-1234")
        self.assertEqual(isolated.openai_base_url, "https://api.openai.com/v1")
        self.assertEqual(isolated.openai_model, "project-model")
        self.assertEqual(isolated.openai_key_fingerprint, "****1234")

    def test_namespaced_deepseek_endpoint_is_rejected(self) -> None:
        environment = {
            "HOUSE_DESIGN_LLM_PROVIDER": "openai",
            "HOUSE_DESIGN_OPENAI_API_KEY": "sk-project-openai-key",
            "HOUSE_DESIGN_OPENAI_BASE_URL": "https://api.deepseek.com/v1",
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(
                ValidationError,
                "HOUSE_DESIGN_OPENAI_BASE_URL must be exactly",
            ):
                Settings(_env_file=None)

    def test_dashscope_namespace_wins_in_polluted_environment(self) -> None:
        environment = {
            "OPENAI_API_KEY": "sk-wrong-global-key",
            "OPENAI_BASE_URL": "https://api.deepseek.com/v1",
            "DASHSCOPE_API_KEY": "sk-wrong-generic-dashscope",
            "HOUSE_DESIGN_LLM_PROVIDER": "dashscope",
            "HOUSE_DESIGN_DASHSCOPE_API_KEY": "sk-dashscope-key-abcd",
            "HOUSE_DESIGN_DASHSCOPE_BASE_URL": (
                "https://dashscope.aliyuncs.com/compatible-mode/v1/"
            ),
            "HOUSE_DESIGN_DASHSCOPE_MODEL": "qwen3.7-plus",
        }
        with patch.dict(os.environ, environment, clear=True):
            isolated = Settings(_env_file=None)

        self.assertEqual(isolated.llm_provider, "dashscope")
        self.assertEqual(isolated.dashscope_api_key, "sk-dashscope-key-abcd")
        self.assertEqual(
            isolated.dashscope_base_url,
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        self.assertEqual(isolated.dashscope_model, "qwen3.7-plus")
        self.assertEqual(isolated.dashscope_key_fingerprint, "****abcd")
        # 通用进程变量与 openai 组完全不参与
        self.assertEqual(isolated.openai_api_key, "")
        self.assertEqual(isolated.active_api_key, "sk-dashscope-key-abcd")
        self.assertEqual(isolated.active_model, "qwen3.7-plus")

    def test_dashscope_wrong_endpoint_is_rejected(self) -> None:
        environment = {
            "HOUSE_DESIGN_LLM_PROVIDER": "dashscope",
            "HOUSE_DESIGN_DASHSCOPE_API_KEY": "sk-dashscope-key",
            "HOUSE_DESIGN_DASHSCOPE_BASE_URL": "https://api.deepseek.com/v1",
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(
                ValidationError,
                "HOUSE_DESIGN_DASHSCOPE_BASE_URL must be exactly",
            ):
                Settings(_env_file=None)

    def test_dashscope_generic_environment_is_ignored(self) -> None:
        polluted_environment = {
            "DASHSCOPE_API_KEY": "sk-generic-dashscope",
            "DASHSCOPE_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "DASHSCOPE_MODEL": "qwen-max",
        }
        with patch.dict(os.environ, polluted_environment, clear=True):
            isolated = Settings(_env_file=None)

        # provider 默认 openai;通用 DASHSCOPE_* 变量必须被忽略
        self.assertEqual(isolated.llm_provider, "openai")
        self.assertEqual(isolated.dashscope_api_key, "")
        self.assertEqual(isolated.active_model, "gpt-5.6-luna")

    def test_ark_namespace_wins_in_polluted_environment(self) -> None:
        environment = {
            "OPENAI_API_KEY": "sk-wrong-global-key",
            "ARK_API_KEY": "sk-wrong-generic-ark",
            "HOUSE_DESIGN_LLM_PROVIDER": "ark",
            "HOUSE_DESIGN_ARK_API_KEY": "ark-project-key-77aa",
            "HOUSE_DESIGN_ARK_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3/",
            "HOUSE_DESIGN_ARK_MODEL": "doubao-seed-2-0-lite-260428",
        }
        with patch.dict(os.environ, environment, clear=True):
            isolated = Settings(_env_file=None)

        self.assertEqual(isolated.llm_provider, "ark")
        self.assertEqual(isolated.ark_api_key, "ark-project-key-77aa")
        self.assertEqual(
            isolated.ark_base_url,
            "https://ark.cn-beijing.volces.com/api/v3",
        )
        self.assertEqual(isolated.ark_model, "doubao-seed-2-0-lite-260428")
        self.assertEqual(isolated.ark_key_fingerprint, "****77aa")
        # 通用进程变量与 openai/dashscope 组完全不参与
        self.assertEqual(isolated.openai_api_key, "")
        self.assertEqual(isolated.dashscope_api_key, "")
        self.assertEqual(isolated.active_api_key, "ark-project-key-77aa")
        self.assertEqual(isolated.active_model, "doubao-seed-2-0-lite-260428")

    def test_ark_wrong_endpoint_is_rejected(self) -> None:
        environment = {
            "HOUSE_DESIGN_LLM_PROVIDER": "ark",
            "HOUSE_DESIGN_ARK_API_KEY": "ark-project-key",
            "HOUSE_DESIGN_ARK_BASE_URL": "https://api.deepseek.com/v1",
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(
                ValidationError,
                "HOUSE_DESIGN_ARK_BASE_URL must be exactly",
            ):
                Settings(_env_file=None)

    def test_ark_generic_environment_is_ignored(self) -> None:
        polluted_environment = {
            "ARK_API_KEY": "ark-generic-key",
            "ARK_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3",
        }
        with patch.dict(os.environ, polluted_environment, clear=True):
            isolated = Settings(_env_file=None)

        # provider 默认 openai;通用 ARK_* 变量必须被忽略
        self.assertEqual(isolated.llm_provider, "openai")
        self.assertEqual(isolated.ark_api_key, "")

    def test_active_model_follows_provider(self) -> None:
        openai_env = {
            "HOUSE_DESIGN_LLM_PROVIDER": "openai",
            "HOUSE_DESIGN_OPENAI_MODEL": "model-a",
        }
        with patch.dict(os.environ, openai_env, clear=True):
            self.assertEqual(Settings(_env_file=None).active_model, "model-a")

        dashscope_env = {
            "HOUSE_DESIGN_LLM_PROVIDER": "dashscope",
            "HOUSE_DESIGN_DASHSCOPE_MODEL": "qwen3.7-plus",
        }
        with patch.dict(os.environ, dashscope_env, clear=True):
            isolated = Settings(_env_file=None)
            self.assertEqual(isolated.active_model, "qwen3.7-plus")
            self.assertEqual(
                isolated.active_base_url,
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            )

    def test_non_openai_provider_is_rejected(self) -> None:
        with patch.dict(
            os.environ,
            {"HOUSE_DESIGN_LLM_PROVIDER": "deepseek"},
            clear=True,
        ):
            with self.assertRaises(ValidationError):
                Settings(_env_file=None)

    def test_generic_langsmith_environment_is_ignored(self) -> None:
        polluted_environment = {
            "LANGSMITH_TRACING": "true",
            "LANGSMITH_API_KEY": "lsv2-global-key",
            "LANGSMITH_ENDPOINT": "https://example.invalid",
            "LANGSMITH_PROJECT": "wrong-project",
        }
        with patch.dict(os.environ, polluted_environment, clear=True):
            isolated = Settings(_env_file=None)

        self.assertFalse(isolated.langsmith_tracing)
        self.assertEqual(isolated.langsmith_api_key, "")
        self.assertEqual(
            isolated.langsmith_endpoint,
            "https://api.smith.langchain.com",
        )
        self.assertEqual(isolated.langsmith_project, "house-design-agent")

    def test_langsmith_tracing_requires_namespaced_key(self) -> None:
        with patch.dict(
            os.environ,
            {"HOUSE_DESIGN_LANGSMITH_TRACING": "true"},
            clear=True,
        ):
            with self.assertRaisesRegex(
                ValidationError,
                "HOUSE_DESIGN_LANGSMITH_API_KEY is required",
            ):
                Settings(_env_file=None)

    def test_langsmith_official_regional_endpoint_is_allowed(self) -> None:
        environment = {
            "HOUSE_DESIGN_LANGSMITH_TRACING": "true",
            "HOUSE_DESIGN_LANGSMITH_API_KEY": "lsv2-project-key-5678",
            "HOUSE_DESIGN_LANGSMITH_ENDPOINT": "https://eu.api.smith.langchain.com/",
            "HOUSE_DESIGN_LANGSMITH_PROJECT": "house-design-eval",
        }
        with patch.dict(os.environ, environment, clear=True):
            isolated = Settings(_env_file=None)

        self.assertTrue(isolated.langsmith_tracing)
        self.assertEqual(
            isolated.langsmith_endpoint,
            "https://eu.api.smith.langchain.com",
        )
        self.assertEqual(isolated.langsmith_project, "house-design-eval")
        self.assertEqual(isolated.langsmith_key_fingerprint, "****5678")

    def test_non_official_langsmith_endpoint_is_rejected(self) -> None:
        environment = {
            "HOUSE_DESIGN_LANGSMITH_ENDPOINT": "https://example.invalid",
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(
                ValidationError,
                "HOUSE_DESIGN_LANGSMITH_ENDPOINT must be an official",
            ):
                Settings(_env_file=None)


if __name__ == "__main__":
    unittest.main()

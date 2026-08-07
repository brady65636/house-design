from pydantic import BaseModel,Field,ValidationError,ConfigDict,model_validator
from typing import Literal
class Target(BaseModel):
    kind:Literal['wall_face','surface']=Field(description='目标类型')
    id:str=Field(min_length=1,description="目标的id")
    model_config = ConfigDict(extra="forbid")

class Assignment(BaseModel):
    target:Target=Field(description='要配置的墙面，地面，或顶面')
    asset_id:str=Field(min_length=1,description='要分配给目标面的资产的id')
    model_config = ConfigDict(extra="forbid")

class Scheme(BaseModel):
    model_config=ConfigDict(extra='forbid')
    assignments:list[Assignment]=Field(description='完整的资产分配列表',min_length=1)
    schema_version:Literal['1.0.0']=Field(description='schema版本')
    scheme_id:str=Field(min_length=1,description="方案唯一的id")
    title:str=Field(min_length=1,description='用户可读的scheme名称')

    @model_validator(mode='after')
    def check_unique_target(self):
        target_list=[(assignment.target.id ,assignment.target.kind) for assignment in self.assignments]
        if len(target_list)!=len(set(target_list)):
            raise ValueError("同一个场景不能重复分配")
        return self




from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, model_validator

# If you have multiple activity param classes, import them here
from runner.activities.ctgan.ac_types import CtganParams
from runner.activities.custom_code.ac_types import CustomCodeParams
from runner.activities.report.ac_types import ReportParams


class Node(BaseModel):
    """
    Represents a DAG node with an activity ID and associated parameters.

    A model-level validator (`model_validator`) is used to automatically 
    convert the `params` dict into the appropriate Pydantic model instance 
    (e.g., CtganParams) based on `activity_id`.

    Note:
    - We declare `params` as Union[dict, CtganParams] (or Any) so we can 
      transform it at validation time.
    """
    activity_id: str
    params: Union[dict, CtganParams, CustomCodeParams, ReportParams] = Field(...)

    @model_validator(mode="before")
    @classmethod
    def convert_params(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dynamically convert 'params' based on 'activity_id' before 
        the Node model is fully validated.
        """
        param_map = {
            "ctgan": CtganParams,
            "custom-code": CustomCodeParams,
            "report": ReportParams,
            # Add additional mappings if you have other activity IDs
            # "some_other_id": SomeOtherParamsClass,
        }

        activity_id = data.get("activity_id")
        raw_params = data.get("params")

        if activity_id in param_map and isinstance(raw_params, dict):
            param_class = param_map[activity_id]
            data["params"] = param_class(**raw_params)

        return data


class Edge(BaseModel):
    """Represents a directed edge between two nodes in the DAG."""
    from_node: Optional[str] = None
    to_node: Optional[str] = None


class DAG(BaseModel):
    """Represents a Directed Acyclic Graph (DAG) of nodes and edges."""
    edges: List[Edge]
    nodes: Dict[str, Node]


class GeneratorParams(BaseModel):
    """Wraps a DAG for execution within a workflow.

    Attributes:
        dag: The Directed Acyclic Graph defining the workflow structure and operations
        userId: Unique identifier of the user initiating the execution
        dataset_id: Dataset used for the current execution
        workflow_id: Id of the workflow blueprint being used
    """
    dag: DAG
    user_id: str
    dataset_id: str
    workflow_id: str


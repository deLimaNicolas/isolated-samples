import asyncio
from datetime import timedelta
from enum import Enum, auto
from typing import Dict, Set, Any, Optional

from temporalio import workflow
from temporalio.common import RetryPolicy
from dotenv import load_dotenv

from .shared import GeneratorParams, Node
from .activities.execution import (
    create_execution_activity,
    patch_execution_activity,
)

load_dotenv()


class Status(Enum):
    PENDING = auto()
    EXECUTING = auto()
    COMPLETED = auto()
    SUCCESS = auto()
    FAILED = auto()
    SKIPPED = auto()

    def __str__(self) -> str:
        return self.name


@workflow.defn(name="IgaraGenerator", sandboxed=False)
class Generator:
    def __init__(self) -> None:
        self.execution_id: Optional[str] = None
        self.user_id: Optional[str] = None
        self.nodes: Dict[str, Node] = {}
        self.edges: list = []
        self.executed_nodes: Dict[str, Dict[str, Any]] = {}
        self._workflow_failed: bool = False
        self._node_dependencies: Dict[str, Set[str]] = {}

    @workflow.run
    async def run(self, data: GeneratorParams) -> Dict[str, Dict[str, Any]]:
        """Main entry point for workflow execution."""
        workflow.logger.info("⚡ Starting IgaraGenerator Workflow...")
        await self.initialize_execution(data)
        await self.process_root_nodes(data)
        await self.finalize_execution()
        return self.executed_nodes

    async def initialize_execution(self, data: GeneratorParams) -> None:
        """Initialize execution record and workflow state."""
        try:
            execution_response = await workflow.execute_activity(
                create_execution_activity,
                args=(
                    data.workflow_id,
                    data.dataset_id,
                    str(Status.PENDING),
                    data.user_id,
                ),
                start_to_close_timeout=timedelta(seconds=30),
            )
            self.execution_id = execution_response["executionId"]
        except workflow.ActivityError as e:
            workflow.logger.error(f"❌ Failed to create execution: {e}")
            raise

        self.user_id = data.user_id
        self.nodes = data.dag.nodes
        self.edges = data.dag.edges
        self._precompute_dependencies()

    def _precompute_dependencies(self) -> None:
        """Precompute node dependencies for faster child processing."""
        self._node_dependencies = {
            node: {
                edge.from_node 
                for edge in self.edges 
                if edge.to_node == node
            }
            for node in self.nodes
        }

    async def process_root_nodes(self, data: GeneratorParams) -> None:
        """Process all root nodes in parallel."""
        root_keys = self.find_root_keys()
        await self.initialize_root_nodes(root_keys)
        await self.update_execution_status(Status.EXECUTING)
        await asyncio.gather(*(self.execute_node(key) for key in root_keys))

    async def initialize_root_nodes(self, root_keys: Set[str]) -> None:
        """Initialize root node states."""
        for key in root_keys:
            await self.update_node_output(key, status=Status.PENDING, result={})

    async def finalize_execution(self) -> None:
        """Finalize workflow execution status."""
        final_status = self.determine_final_status()
        await self.update_execution_status(final_status)

    def determine_final_status(self) -> Status:
        """Determine final workflow status based on node outcomes."""
        statuses = [node["status"] for node in self.executed_nodes.values()]
        
        if any(status == Status.FAILED.name for status in statuses):
            return Status.FAILED
        if any(status == Status.PENDING.name for status in statuses):
            return Status.PENDING
        return Status.COMPLETED

    async def update_execution_status(self, status: Status) -> None:
        """Update execution status in persistence layer."""
        if not self.execution_id:
            return
        
        patch = [{"op": "replace", "path": "/status", "value": str(status)}]
        await workflow.execute_activity(
            patch_execution_activity,
            args=(self.execution_id, patch, self.user_id),
            start_to_close_timeout=timedelta(seconds=30),
        )

    async def update_node_output(
        self,
        node_key: str,
        result: Optional[dict] = None,
        status: Optional[Status] = None
    ) -> None:
        """Update node output in persistence layer."""
        if not self.execution_id:
            return

        patches = []
        if result is not None:
            patches.append({
                "op": "add",
                "path": f"/output/{node_key}",
                "value": result
            })
        if status is not None:
            patches.append({
                "op": "add",
                "path": f"/output/{node_key}/status",
                "value": str(status)
            })

        await workflow.execute_activity(
            patch_execution_activity,
            args=(self.execution_id, patches, self.user_id),
            start_to_close_timeout=timedelta(seconds=30),
        )

    async def execute_node(self, node_key: str) -> None:
        """Execute a single node and handle its children."""
        if self._workflow_failed:
            await self._handle_skipped_node(node_key)
            return

        await self._process_node_execution(node_key)

    async def _handle_skipped_node(self, node_key: str) -> None:
        """Mark node as skipped due to workflow failure."""
        result = {"error": "Skipped due to previous node failure"}
        self.executed_nodes[node_key] = {
            "status": Status.SKIPPED.name,
            "output": result
        }
        await self.update_node_output(
            node_key,
            status=Status.SKIPPED,
            result=result
        )

    async def _process_node_execution(self, node_key: str) -> None:
        """Execute node logic and handle results."""
        node = self.nodes[node_key]
        node.params.node_name = node_key
        
        await self.update_node_output(node_key, status=Status.EXECUTING, result={})

        try:
            result = await workflow.execute_activity(
                node.activity_id,
                node.params,
                start_to_close_timeout=timedelta(seconds=900),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            await self._handle_successful_execution(node_key, result)
        except Exception as e:
            await self._handle_failed_execution(node_key, e)
            return

        await self._process_child_nodes(node_key)

    async def _handle_successful_execution(self, node_key: str, result: Any) -> None:
        """Handle successful node execution."""
        self.executed_nodes[node_key] = {
            "status": Status.SUCCESS.name,
            "output": result
        }
        await self.update_node_output(
            node_key,
            result=result,
            status=Status.SUCCESS
        )

    async def _handle_failed_execution(self, node_key: str, error: Exception) -> None:
        """Handle failed node execution."""
        workflow.logger.error(f"❌ Execution Failed for Node {node_key}: {error}")
        error_result = {"error": str(error)}
        self.executed_nodes[node_key] = {
            "status": Status.FAILED.name,
            "output": error_result
        }
        await self.update_node_output(
            node_key,
            result=error_result,
            status=Status.FAILED
        )
        self._workflow_failed = True

    async def _process_child_nodes(self, node_key: str) -> None:
        """Process child nodes after successful parent execution."""
        if self._workflow_failed:
            return

        children = {
            edge.to_node 
            for edge in self.edges
            if edge.from_node == node_key
        }
        ready_children = [
            child for child in children
            if all(
                dep in self.executed_nodes
                for dep in self._node_dependencies.get(child, set())
            )
        ]
        await asyncio.gather(*(self.execute_node(child) for child in ready_children))

    def find_root_keys(self) -> Set[str]:
        """Identify nodes with no incoming edges."""
        all_nodes = set(self.nodes.keys())
        child_nodes = {edge.to_node for edge in self.edges}
        return all_nodes - child_nodes

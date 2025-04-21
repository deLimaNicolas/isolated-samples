from managers.installer_manager import InstallerManager
class HelmfileWorkflow:
    @staticmethod
    def restart_deployments(namespace: str, context: str) -> None:
        """
        Restarts deployments in the specified namespace for both MAIN and EXCHANGE clusters.

        Args:
            namespace (str): The namespace where deployments are located.
            context (str): The context or name of the cluster.
        """
        print(
            f"🚀 Restarting deployments in namespace: {namespace} for cluster: {context}"
        )

        installer_manager = InstallerManager({"context": context})

        print("🔧 Selecting MAIN cluster...")
        installer_manager.select_cluster(cluster_type="MAIN")
        print(f"🔄 Restarting deployments in MAIN cluster for namespace: {namespace}")
        installer_manager.k8s_manager.restart_deployments(namespace)

        print("🔧 Selecting EXCHANGE cluster...")
        installer_manager.select_cluster(cluster_type="EXCHANGE")
        print(
            f"🔄 Restarting deployments in EXCHANGE cluster for namespace: {namespace}"
        )
        installer_manager.k8s_manager.restart_deployments(namespace)

        print(f"✅ Deployments restarted successfully for namespace: {namespace}")


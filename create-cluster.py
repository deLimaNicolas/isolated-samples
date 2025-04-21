from managers.installer_manager import InstallerManager
from workflows.terraform.workflow_util import (
    create_k8s_main_file,
    create_backend_terraform,
)


class ClusterWorkflow:
    @staticmethod
    def install_cluster(context: str, dryrun: bool, update: bool = False, install_sftp: bool = False) -> None:
        """
        Installs a Kubernetes cluster using Terraform.

        Args:
            context (str): The context or name of the cluster.
            update (bool): Whether to create or not a new bucket since it could be an existing env
            dryrun (bool): If True, performs a dry run (plan only). If False, applies the changes.
        """
        print(f"🚀 Starting cluster installation for: {context} | --update {update}")

        installer_manager = InstallerManager({"context": context})

        print(f"📝 Generating Terraform configuration files for: {context}")
        create_k8s_main_file(context, installer_manager.terraform_path)
        create_backend_terraform(context, installer_manager.terraform_path)

        if not update:
            print(
                f"🪣 Creating GCS bucket for Terraform state: {context}-bucket-tfstate"
            )
            installer_manager.gcp_manager.create_bucket(
                name=f"{context}-bucket-tfstate"
            )

        print("🔧 Initializing Terraform...")
        installer_manager.terraform_manager.init()

        if dryrun:
            print("🔍 Running dry run (plan only)...")
            installer_manager.terraform_manager.plan(target="module.k8s_cluster")
            installer_manager.terraform_manager.plan(target="module.init_charts")
            if install_sftp:
                installer_manager.terraform_manager.plan(target="module.sftp")


            print(f"🧹 Cleaning up GCS bucket after dry run: {context}-bucket-tfstate")
            installer_manager.gcp_manager.delete_bucket(
                name=f"{context}-bucket-tfstate"
            )
        else:
            print("🚀 Applying Terraform changes...")
            installer_manager.terraform_manager.apply(target="module.k8s_cluster")
            installer_manager.terraform_manager.apply(target="module.init_charts")
            if install_sftp:
                installer_manager.terraform_manager.apply(target="module.sftp")
            print(f"✅ Cluster installation completed successfully for: {context}")

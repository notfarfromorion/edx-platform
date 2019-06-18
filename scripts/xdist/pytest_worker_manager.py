import argparse
import logging
import time

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PytestWorkerManager():
    """
    Responsible for spinning up and terminating EC2 workers to be used with pytest-xdist
    """
    WORKER_RUN_TIMEOUT_MINUTES = 10
    MAX_RUN_WORKER_RETRIES = 7

    def __init__(self, region):
        self.ec2 = boto3.client('ec2', region)

    def spin_up_workers(self, number_of_workers, ami, instance_type, subnet, security_group_ids, key_name, iam_instance_profile):
        """
        Spins up workers and generates two .txt files, containing the IP/ arns
        of the new tasks.
        """
        logging.info("Spinning up {} workers".format(number_of_workers))

        worker_instance_ids = []
        for retry in range(1, self.MAX_RUN_WORKER_RETRIES + 1):
            try:
                response = self.ec2.run_instances(
                    MinCount=number_of_workers,
                    MaxCount=number_of_workers,
                    ImageId=ami,
                    InstanceType=instance_type,
                    SubnetId=subnet,
                    SecurityGroupIds=security_group_ids,
                    IamInstanceProfile={
                        "Arn": iam_instance_profile
                    },
                    KeyName=key_name,
                    TagSpecifications=[
                        {
                            'ResourceType': 'instance',
                            'Tags': [
                                {"Key": "master", "Value": "build.testeng.edx.org"},
                                {"Key": "worker", "Value": "pytest_xdist_worker"}
                            ]
                        }
                    ]
                )
            except ClientError as err:
                # Handle AWS throttling with an exponential backoff
                if retry == self.MAX_RUN_WORKER_RETRIES:
                    raise StandardError(
                        "MAX_RUN_WORKER_RETRIES ({}) reached while spinning up tasks due to AWS throttling.".format(self.MAX_RUN_WORKER_RETRIES)
                    )
                logger.info("Hit error: {}. Retrying".format(err))
                countdown = 2 ** retry
                logger.info("Sleeping for {} seconds".format(countdown))
                time.sleep(countdown)
            else:
                break

        for instance_response in response['Instances']:
            worker_instance_ids.append(instance_response['InstanceId'])

        # Wait for workers to finish spinning up
        not_running = worker_instance_ids[:]
        ip_addresses = []
        all_running = False
        for attempt in range(0, self.WORKER_RUN_TIMEOUT_MINUTES * 2):
            time.sleep(5)
            list_workers_response = self.ec2.describe_instances(InstanceIds=not_running)
            del not_running[:]
            for reservations in list_workers_response['Reservations']:
                for instance_info in reservations['Instances']:
                    if instance_info['State']['Name'] == "running":
                        ip_addresses.append(instance_info['PrivateIpAddress'])
                    else:
                        not_running.append(instance_info['InstanceId'])

            if len(not_running) > 0:
                logger.info("Still waiting on {} workers to spin up".format(len(not_running)))
            else:
                logger.info("Finished spinning up workers")
                all_running = True
                break

        if not all_running:
            raise StandardError(
                "Timed out waiting to spin up all workers."
            )

        logger.info("Successfully booted up {} workers.".format(number_of_workers))

        # Generate .txt files containing IP addresses and instance ids
        ip_list_string = ",".join(ip_addresses)
        logger.info("Worker IP list: {}".format(ip_list_string))
        ip_list_file = open("pytest_worker_ips.txt", "w")
        ip_list_file.write(ip_list_string)
        ip_list_file.close()

        worker_instance_id_list_string = ",".join(worker_instance_ids)
        logger.info("Worker Instance Id list: {}".format(worker_instance_id_list_string))
        task_arn_file = open("pytest_worker_instance_ids.txt", "w")
        task_arn_file.write(worker_instance_id_list_string)
        task_arn_file.close()

    def terminate_workers(self, worker_instance_ids):
        """
        Terminates workers based on a list of worker_instance_ids.
        """
        instance_id_list = worker_instance_ids.split(',')
        response = self.ec2.terminate_instances(
            InstanceIds=instance_id_list
        )


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="PytestWorkerManager, manages EC2 workers in an AWS cluster."
    )

    parser.add_argument('--action', '-a', choices=['up', 'down'], default=None,
                        help="Action for PytestWorkerManager to perform. "
                        "Either up for spinning up AWS EC2 workers or down for terminating them")

    parser.add_argument('--region', '-g', default='us-east-1',
                        help="AWS region where EC2 infrastructure lives. Defaults to us-east-1")

    # Spinning up workers
    parser.add_argument('--num-workers', '-n', type=int, default=None,
                        help="Number of EC2 workers to spin up")

    parser.add_argument('--ami', '-ami', default=None,
                        help="AMI for workers")

    parser.add_argument('--instance-type', '-type', default=None,
                        help="Desired EC2 instance type")

    parser.add_argument('--subnet-id', '-s', default=None,
                        help="Subnet for the workers to exist in")

    parser.add_argument('--security_groups', '-sg', nargs='+', default=None,
                        help="List of security group ids to apply to workers")

    parser.add_argument('--key-name', '-key', default=None,
                        help="Key pair name for sshing to worker")

    parser.add_argument('--iam-arn', '-iam', default=None,
                        help="Iam Instance Profile ARN for the workers")

    # Terminating tasks
    parser.add_argument('--instance-ids', '-ids', default=None,
                        help="Instance ids terminate")

    args = parser.parse_args()
    containerManager = PytestWorkerManager(args.region)

    if args.action == 'up':
        containerManager.spin_up_workers(
            args.num_workers,
            args.ami,
            args.instance_type,
            args.subnet_id,
            args.security_groups,
            args.key_name,
            args.iam_arn
        )
    elif args.action == 'down':
        containerManager.terminate_tasks(
            args.instance_ids
        )
    else:
        logger.info("No action specified for PytestWorkerManager")

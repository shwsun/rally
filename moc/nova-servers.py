# Copyright 2018 Mass Open Cloud
#
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import jsonschema

from rally.common import logging
from rally import consts
from rally import exceptions as rally_exceptions
from rally.plugins.openstack import scenario
from rally.plugins.openstack.scenarios.cinder import utils as cinder_utils
from rally.plugins.openstack.scenarios.neutron import utils as neutron_utils
from rally.plugins.openstack.scenarios.nova import utils
from rally.plugins.openstack.wrappers import network as network_wrapper
from rally.task import types
from rally.task import validation


"""Complex Nova Scenarios for benchmarking Pythia."""


LOG = logging.getLogger(__name__)


@types.convert(image={"type": "glance_image"},
               flavor={"type": "nova_flavor"})
@validation.add("image_valid_on_flavor", flavor_param="flavor",
                image_param="image", validate_disk=False)
@validation.add("required_services", services=([consts.Service.NOVA,
                                                consts.Service.CINDER]))
@validation.add("required_platform", platform="openstack", admin=True,
                users=True)
@scenario.configure(context={"cleanup@openstack": ["nova", 'cinder']},
                    name="NovaServers.stitched_complex_workload",
                    platform="openstack")
class StitchedComplexWorkload(utils.NovaScenario, cinder_utils.CinderBasic):
    """Complex workload for benchmarking Pythia framework.

    The workload will:
    1. boot a list of servers (number == count),
    2. creates a value and then boot a server from that volume,
    3. boot a server and then run some specific commands against it

    """

    def run(self, image, flavor, volume_size, volume_type=None, count=5,
            min_sleep=0, max_sleep=0, detailed=True, force_delete=False,
            actions=None, **kwargs):
        """Boot a server from volume and then delete it.

        task 1: BootAndDeleteMultipleServers
        task 2: BootServerFromVolumeAndDelete
        task 3: BootAndBounceServer

        """

        # task 1
        servers = self._boot_servers(image, flavor, 1, instances_amount=count,
                                     **kwargs)
        self.sleep_between(min_sleep, max_sleep)
        self._list_servers(detailed)
        self._delete_servers(servers, force=force_delete)

        # task 2
        volume_two = self.cinder.create_volume(volume_size, imageRef=image,
                                               volume_type=volume_type)
        block_device_mapping = {"vda": "%s:::1" % volume_two.id}
        server_two = self._boot_server(None, flavor,
                                       block_device_mapping=block_device_mapping,
                                       **kwargs)
        self.sleep_between(min_sleep, max_sleep)
        self._list_servers(detailed)
        self._delete_server(server_two, force=force_delete)

        # task 3
        action_builder = self._bind_actions()
        actions = actions or []
        try:
            action_builder.validate(actions)
        except jsonschema.exceptions.ValidationError as error:
            raise rally_exceptions.InvalidConfigException(
                "Invalid server actions configuration \'%(actions)s\' due to: "
                "%(error)s" % {"actions": str(actions), "error": str(error)})
        server_three = self._boot_server(image, flavor, **kwargs)
        for action in action_builder.build_actions(actions, server_three):
            action()
        self._delete_server(server_three, force=force_delete)


@types.convert(image={"type": "glance_image"},
               flavor={"type": "nova_flavor"})
@validation.add("image_valid_on_flavor", flavor_param="flavor",
                image_param="image", validate_disk=False)
@validation.add("required_services", services=([consts.Service.NOVA,
                                                consts.Service.GLANCE,
                                                consts.Service.CINDER]))
@validation.add("required_platform", platform="openstack", admin=True,
                users=True)
@scenario.configure(context={"cleanup@openstack": ["nova", 'cinder', 'glance']},
                    name="NovaServers.mixed_complex_workload_one",
                    platform="openstack")
class MixedComplexWorkloadOne(utils.NovaScenario, cinder_utils.CinderBasic):
    """Mixed complex workload for benchmarking Pythia framework.

    This workload is derived from the StichedComplexWorkload. It will:
    1. boot a list of servers (# == count) from the volumes, execute operations
    against them, and then take snapshots for all of them,

    1. boot a list of servers (number == count),
    2. creates a value and then boot a server from that volume,
    3. boot a server and then run some specific commands against it

    """

    def run(self, image, flavor, volume_size, volume_type=None, count=5,
            min_sleep=0, max_sleep=0, detailed=True, force_delete=False,
            auto_assign_nic=False, actions=None, **kwargs):
        """Boot a server from volume and then delete it.

        task 1: BootAndDeleteMultipleServers
        task 2: BootServerFromVolumeAndDelete (scratched)
        task 3: BootAndBounceServer
        task 4: SnapshotServer
        """
        server_list = []
        #volume_list = []
        snapshot_list = []
        snapshot_server_list = []

        self._list_servers(detailed)

        for x in range(0, count):
            # create volume to boot server from
            #volume = self.cinder.create_volume(volume_size, imageRef=image,
            #                                   volume_type=volume_type)
            #volume_list.append(volume)
            #block_device_mapping = {"vda": "%s:::1" % volume.id}
            #self.sleep_between(min_sleep, max_sleep)
            # check
            #server = self._boot_server(None, flavor,
            #                           auto_assign_nic=auto_assign_nic,
            #                           block_device_mapping=block_device_mapping,
            #                           **kwargs)
            server = self._boot_server(image, flavor, **kwargs)
            self.sleep_between(min_sleep, max_sleep)
            server_list.append(server)
            # create a list of operations to execute
            action_builder = self._bind_actions()
            actions = actions or []
            try:
                action_builder.validate(actions)
            except jsonschema.exceptions.ValidationError as error:
                raise rally_exceptions.InvalidConfigException(
                    "Invalid server actions configuration \'%(actions)s\' due to: "
                    "%(error)s" % {"actions": str(actions), "error": str(error)})
            # exec operations against the server desired
            for action in action_builder.build_actions(actions, server):
                action()

            # snapshotting
            # NOTE(jethros): booting servers from snapshots will double the
            # number of VMs
            snapshot = self._create_image(server)
            snapshot_list.append(snapshot)
            server_new = self._boot_server(snapshot.id, flavor, **kwargs)
            snapshot_server_list.append(server_new)
            self.sleep_between(min_sleep, max_sleep)
            self._list_servers(detailed)

        # cleanup
        for server in server_list:
            self._delete_server(server, force=force_delete)

        for snapshot in snapshot_list:
            self._delete_image(snapshot)

        for snapshot_server in snapshot_server_list:
            self._delete_server(snapshot_server, force=force_delete)


@types.convert(image={"type": "glance_image"},
               flavor={"type": "nova_flavor"})
@validation.add("image_valid_on_flavor", flavor_param="flavor",
                image_param="image", validate_disk=False)
@validation.add("required_services", services=([consts.Service.NOVA,
                                                consts.Service.GLANCE,
                                                consts.Service.CINDER]))
@validation.add("required_platform", platform="openstack", admin=True,
                users=True)
@scenario.configure(context={"cleanup@openstack": ["nova", 'cinder', 'glance']},
                    name="NovaServers.mixed_complex_workload_one_backup",
                    platform="openstack")
class MixedComplexWorkloadOneBackup(utils.NovaScenario, cinder_utils.CinderBasic):
    """Mixed complex workload for benchmarking Pythia framework.

    This workload is derived from the StichedComplexWorkload. It will:
    1. boot a list of servers (# == count) from the volumes, execute operations
    against them, and then take snapshots for all of them,

    1. boot a list of servers (number == count),
    2. creates a value and then boot a server from that volume,
    3. boot a server and then run some specific commands against it

    """

    def run(self, image, flavor, volume_size, volume_type=None, count=5,
            min_sleep=0, max_sleep=0, detailed=True, force_delete=False,
            auto_assign_nic=False, actions=None, **kwargs):
        """Boot a server from volume and then delete it.

        task 1: BootAndDeleteMultipleServers
        task 2: BootServerFromVolumeAndDelete
        task 3: BootAndBounceServer
        task  SnapshotServer
        """
        server_list = []
        volume_list = []
        snapshot_list = []
        snapshot_server_list = []

        self._list_servers(detailed)

        for x in range(0, count):
            # create volume to boot server from
            volume = self.cinder.create_volume(volume_size, imageRef=image,
                                               volume_type=volume_type)
            volume_list.append(volume)
            block_device_mapping = {"vda": "%s:::1" % volume.id}
            self.sleep_between(min_sleep, max_sleep)
            # check
            #server= self._boot_server(image, flavor, **kwargs)
            server = self._boot_server(None, flavor,
                                       auto_assign_nic=auto_assign_nic,
                                       block_device_mapping=block_device_mapping,
                                       **kwargs)
            self.sleep_between(min_sleep, max_sleep)
            server_list.append(server)
            # create a list of operations to execute
            action_builder = self._bind_actions()
            actions = actions or []
            try:
                action_builder.validate(actions)
            except jsonschema.exceptions.ValidationError as error:
                raise rally_exceptions.InvalidConfigException(
                    "Invalid server actions configuration \'%(actions)s\' due to: "
                    "%(error)s" % {"actions": str(actions), "error": str(error)})
            # exec operations against the server desired
            for action in action_builder.build_actions(actions, server):
                action()

            # snapshotting
            snapshot = self._create_image(server)
            snapshot_list.append(snapshot)
            server_new = self._boot_server(snapshot.id, flavor, **kwargs)
            snapshot_server_list.append(server_new)
            self.sleep_between(min_sleep, max_sleep)
            self._list_servers(detailed)

        # cleanup
        for server in server_list:
            self._delete_server(server, force=force_delete)

        for snapshot in snapshot_list:
            self._delete_image(snapshot)

        for snapshot_server in snapshot_server_list:
            self._delete_server(snapshot_server, force=force_delete)




@types.convert(image={"type": "glance_image"},
               flavor={"type": "nova_flavor"},
               to_flavor={"type": "nova_flavor"})
@validation.add("image_valid_on_flavor", flavor_param="flavor",
                image_param="image", validate_disk=False)
@validation.add("required_services", services=([consts.Service.NOVA,
                                                consts.Service.GLANCE,
                                                consts.Service.CINDER]))
@validation.add("required_platform", platform="openstack", admin=True,
                users=True)
@scenario.configure(context={"cleanup@openstack": ["nova", 'cinder', 'glance']},
                    name="NovaServers.mixed_complex_workload_two",
                    platform="openstack")
class MixedComplexWorkloadTwo(utils.NovaScenario, cinder_utils.CinderBasic):
    """Mixed complex workload for benchmarking Pythia framework.

    This workload will:
    1. boot a VM,
    2. run operations against the VM
    3. resize the vm
    4. re-run the pervious operations,
    5. snapshot the vm into a image
    6. boot another vm from the image


    """

    def run(self, image, flavor, to_flavor, volume_size, volume_type=None,
            count=2, confirm=True, do_delete=True, min_sleep=0, max_sleep=0,
            detailed=True, 
            force_delete=False, actions=None, **kwargs):
        """Boot a server from volume and then delete it.

        task 1: BootAndDeleteMultipleServers
        task 2: BootServerFromVolumeAndDelete
        task 3: BootAndBounceServer
        task  SnapshotServer
        ResizeServer

        NEXT:
        BootServerAttachCreatedVolumeAndResize
        BootServerAttachVolumeAndListAttachments
        BootAndRebuildServer
        """
        server_list = []
        snapshot_list = []
        snapshot_server_list = []

        self._list_servers(detailed)

        for x in range(0, count):
            server = self._boot_server(image, flavor, **kwargs)
            self.sleep_between(min_sleep, max_sleep)
            server_list.append(server)

            # create a list of operations to execute
            action_builder = self._bind_actions()
            actions = actions or []
            try:
                action_builder.validate(actions)
            except jsonschema.exceptions.ValidationError as error:
                raise rally_exceptions.InvalidConfigException(
                    "Invalid server actions configuration \'%(actions)s\' due to: "
                    "%(error)s" % {"actions": str(actions), "error": str(error)})
            # exec operations against the server desired
            for action in action_builder.build_actions(actions, server):
                action()

            # Try to resize it
            self._resize(server, to_flavor)
            # by default we confirm
            confirm = kwargs.get("confirm", True)
            if confirm:
                self._resize_confirm(server)
            else:
                self._resize_revert(server)

            # re-run the operations
            for action in action_builder.build_actions(actions, server):
                action()

            # snapshotting
            snapshot = self._create_image(server)
            snapshot_list.append(snapshot)
            #server_new = self._boot_server(snapshot.id, flavor, **kwargs)
            #snapshot_server_list.append(server_new)
            self.sleep_between(min_sleep, max_sleep)
            self._list_servers(detailed)

        # cleanup
        for server in server_list:
            self._delete_server(server, force=force_delete)

        for snapshot in snapshot_list:
            self._delete_image(snapshot)

        #for snapshot_server in snapshot_server_list:
        #    self._delete_server(snapshot_server, force=force_delete)

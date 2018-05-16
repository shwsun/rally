# Copyright 2014: Mirantis Inc.
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

from rally.common import cfg
from rally.common import logging
from rally.plugins.openstack import scenario
from rally.plugins.openstack.wrappers import glance as glance_wrapper
from rally.task import atomic
from rally.task import utils


CONF = cfg.CONF
LOG = logging.getLogger(__name__)

# -------------------------------------------------
# NOTE(jethro): Sampling functiobn.
# -------------------------------------------------
import random
import subprocess
from osprofiler import profiler


def is_sampled(rate):
    MAX_RANGE = 100
    if random.randint(0, 100) < MAX_RANGE * rate:
        return True
    return False


SAMPLING_RATE = 1  # 20% sampling rate



class GlanceScenario(scenario.OpenStackScenario):
    """Base class for Glance scenarios with basic atomic actions."""

    def __init__(self, context=None, admin_clients=None, clients=None):
        super(GlanceScenario, self).__init__(context, admin_clients, clients)
        LOG.warning(
            "Class %s is deprecated since Rally 0.10.0 and will be removed "
            "soon. Use "
            "rally.plugins.openstack.services.image.image.Image "
            "instead." % self.__class__)

    @atomic.action_timer("glance.list_images")
    def _list_images(self):
        """Returns user images list."""
        return list(self.clients("glance").images.list())

    @atomic.action_timer("glance.create_image")
    def _create_image(self, container_format, image_location, disk_format,
                      **kwargs):
        """Create a new image.

        :param container_format: container format of image. Acceptable
                                 formats: ami, ari, aki, bare, and ovf
        :param image_location: image file location
        :param disk_format: disk format of image. Acceptable formats:
                            ami, ari, aki, vhd, vmdk, raw, qcow2, vdi, and iso
        :param kwargs: optional parameters to create image

        :returns: image object
        """
        LOG.warning("TRACE: _create_image")
        self._init_profiler(self.context)

        if not kwargs.get("name"):
            kwargs["name"] = self.generate_random_name()
        client = glance_wrapper.wrap(self._clients.glance, self)
        return client.create_image(container_format, image_location,
                                   disk_format, **kwargs)

    @atomic.action_timer("glance.delete_image")
    def _delete_image(self, image):
        """Deletes given image.

        Returns when the image is actually deleted.

        :param image: Image object
        """
        LOG.warning("TRACE: _delete_image")
        self._init_profiler(self.context)

        self.clients("glance").images.delete(image.id)
        wrapper = glance_wrapper.wrap(self._clients.glance, self)
        utils.wait_for_status(
            image, ["deleted", "pending_delete"],
            check_deletion=True,
            update_resource=wrapper.get_image,
            timeout=CONF.openstack.glance_image_delete_timeout,
            check_interval=CONF.openstack.glance_image_delete_poll_interval)

    def _init_profiler(self, context):
        """Inits the profiler."""
        LOG.warning("DEBUG: _init_profiler")
        if not CONF.openstack.enable_profiler:
            return
        if context is not None:
            cred = None
            profiler_hmac_key = None
            profiler_conn_str = None
            if context.get("admin"):
                cred = context["admin"]["credential"]
                if cred.profiler_hmac_key is not None:
                    profiler_hmac_key = cred.profiler_hmac_key
                    profiler_conn_str = cred.profiler_conn_str
            if context.get("user"):
                cred = context["user"]["credential"]
                if cred.profiler_hmac_key is not None:
                    profiler_hmac_key = cred.profiler_hmac_key
                    profiler_conn_str = cred.profiler_conn_str
            # NOTE(jethro): changes to add the sampling decision
            if profiler_hmac_key is None:
                if is_sampled(SAMPLING_RATE) is True:
                    profiler_hmac_key = "Devstack1"
                    pass
                else:
                    return
            profiler.init(profiler_hmac_key)
            trace_id = profiler.get().get_base_id()
            print("TRACE: ID %s") % trace_id
            LOG.info("TRACE: ID %s" % (trace_id))
            complete_data = {"title": "OSProfiler Trace-ID",
                             "chart_plugin": "OSProfiler",
                             "data": {"trace_id": [trace_id],
                                      "conn_str": profiler_conn_str}}
            self.add_output(complete=complete_data)

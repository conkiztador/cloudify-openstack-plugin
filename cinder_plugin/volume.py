#########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  * See the License for the specific language governing permissions and
#  * limitations under the License.

import time

from cloudify import ctx
from cloudify.decorators import operation
from cloudify import exceptions as cfy_exc

from openstack_plugin_common import (delete_runtime_properties,
                                     is_external_resource,
                                     with_cinder_client,
                                     get_default_resource_id,
                                     transform_resource_name,
                                     use_external_resource,
                                     COMMON_RUNTIME_PROPERTIES_KEYS,
                                     OPENSTACK_ID_PROPERTY,
                                     OPENSTACK_TYPE_PROPERTY)

VOLUME_OPENSTACK_TYPE = 'volume'
VOLUME_DEVICE_NAME = 'volume_device_name'

VOLUME_STATUS_CREATING = 'creating'
VOLUME_STATUS_DELETING = 'deleting'
VOLUME_STATUS_AVAILABLE = 'available'
VOLUME_STATUS_IN_USE = 'in-use'
VOLUME_STATUS_ERROR = 'error'
VOLUME_STATUS_ERROR_DELETING = 'error_deleting'
VOLUME_ERROR_STATUSES = (VOLUME_STATUS_ERROR, VOLUME_STATUS_ERROR_DELETING)


@operation
@with_cinder_client
def create(cinder_client, **kwargs):
    resource_id = ctx.properties['resource_id']
    ctx.runtime_properties[VOLUME_DEVICE_NAME] = ctx.properties['device_name']

    volume = use_external_resource(ctx, cinder_client, VOLUME_OPENSTACK_TYPE)

    if volume is None:
        name = resource_id or get_default_resource_id(ctx,
                                                      VOLUME_OPENSTACK_TYPE)
        name = transform_resource_name(ctx, name)
        volume_dict = {'display_name': name}
        volume_dict.update(ctx.properties['volume'])

        v = cinder_client.volumes.create(**volume_dict)

        ctx.runtime_properties[OPENSTACK_ID_PROPERTY] = v.id
        ctx.runtime_properties[OPENSTACK_TYPE_PROPERTY] = \
            VOLUME_OPENSTACK_TYPE
        wait_until_status(cinder_client=cinder_client,
                          volume_id=v.id,
                          status=VOLUME_STATUS_AVAILABLE)


@operation
@with_cinder_client
def delete(cinder_client, **kwargs):
    if not is_external_resource(ctx):
        volume_id = ctx.runtime_properties.get(OPENSTACK_ID_PROPERTY)
        cinder_client.volumes.delete(volume_id)
    delete_runtime_properties(ctx, COMMON_RUNTIME_PROPERTIES_KEYS)


@with_cinder_client
def wait_until_status(cinder_client, volume_id, status, num_tries=10,
                      timeout=2):
    for _ in range(num_tries):
        volume = cinder_client.volumes.get(volume_id)

        if volume.status in VOLUME_ERROR_STATUSES:
            raise cfy_exc.NonRecoverableError(
                "Volume {0} is in error state".format(volume_id))

        if volume.status == status:
            return volume, True
        time.sleep(timeout)

    ctx.logger.warning("Volume {0} current state: '{1}', "
                       "expected state: '{2}'".format(volume_id,
                                                      volume.status,
                                                      status))
    return volume, False


@with_cinder_client
def get_attachment(cinder_client, volume_id, server_id):
    volume = cinder_client.volumes.get(volume_id)
    for attachment in volume.attachments:
        if attachment['server_id'] == server_id:
            return attachment

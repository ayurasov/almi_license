"""Instance identifiers of products that do not send a UUID (E11-01, E11-03).

The namespaces must never change: they turn the same instanceId or machine hash into the same
instance_id, so that a repeated request does not take another seat.
"""

from uuid import NAMESPACE_URL, UUID, uuid5

NAMESPACE_ALMI = uuid5(NAMESPACE_URL, "https://license.alter-os.ru/ns/server-instance")
NAMESPACE_ALMI_OS = uuid5(NAMESPACE_URL, "https://license.alter-os.ru/ns/os-node")


def server_instance_id(instance_id: str) -> UUID:
    return uuid5(NAMESPACE_ALMI, instance_id)


def os_node_id(machine_hash: str) -> UUID:
    return uuid5(NAMESPACE_ALMI_OS, machine_hash.lower())


__author__ = 'nmarchenko'

from fabric.api import local, run, env, sudo

# 10.20.0.1/24   - Mirantis OpenStack Admin network
# 172.16.0.1/24  - OpenStack Public/External/Floating network
# 172.16.1.1/24  - OpenStack Fixed/Internal/Private network

OVS_ADMIN_BR = 'fuel_admin_br'
OVS_PUBLIC_BR = 'fuel_public_br'
OVS_PRIVATE_BR = 'fuel_private_br'

GRE_KEY = {
    OVS_ADMIN_BR: 1,
    OVS_PUBLIC_BR: 2,
    OVS_PRIVATE_BR: 3
}


VIRTUALBOX_ADMIN_BR_IP = '10.20.0.1'
VIRTUALBOX_PUBLIC_BR_IP = '172.16.0.254'
VIRTUALBOX_PRIVATE_BR_IP = '172.16.1.1'


NODE = '172.18.214.15'


def _fuel_master_available():
    return 'fuel-master' in local('VBoxManage list vms | grep fuel', capture=True)


def _slave_list():
    result = local('VBoxManage list vms | grep fuel-slave', capture=True)
    return [line.split(' ')[0].strip('"') for line in result.splitlines()]


def set_bridge(vm, nic, bridge_name):
    local('VBoxManage modifyvm {} --nic{} bridged'.format(vm, nic))
    local('VBoxManage modifyvm {} --bridgeadapter{} {}'.format(vm, nic, bridge_name))


def tap_name(vm, nic):
    return 'ftap_{}_{}'.format(vm, nic)


def create_and_attach_tap(tap_name, bridge):
    local('sudo ip tuntap add mode tap {}'.format(tap_name))
    local('sudo ip link set {} up'.format(tap_name))
    local('sudo ovs-vsctl add-port {} {}'.format(bridge, tap_name))


def create_brige(name):
    local('sudo ovs-vsctl --may-exist add-br {}'.format(name))
    local('sudo ovs-vsctl --may-exist add-port {} gre{} -- '
          'set interface gre{} type=gre options:remote_ip="{} key={}"'.format(name, GRE_KEY[name], GRE_KEY[name], NODE, GRE_KEY[name]))


def find_virtual_box_bridges():
    hostonlyifs = \
        local('VBoxManage list -l hostonlyifs | '
              'grep -e "10\.20\.0\.1" -e "172\.16\.0\.254" -e "172\.16\.1\.1" -B3 | '
              'grep -e "Name" -e "IPAddress" '
              '| awk -F " " \'{print $2}\'', capture=True)

    chain = (VIRTUALBOX_ADMIN_BR_IP, VIRTUALBOX_PUBLIC_BR_IP, VIRTUALBOX_PRIVATE_BR_IP)

    i = iter(hostonlyifs.splitlines())

    result = range(0, 3)

    for _ in range(0, 3):
        name, ip = i.next(), i.next()
        result[chain.index(ip)] = name

    return result


def delete_tap(tap_name, bridge):

    local('sudo ovs-vsctl --if-exists del-port {} {}'.format(bridge, tap_name))

    try:
        local('sudo ip tuntap del mode tap {}'.format(tap_name))
    except:
        pass


def clear_routes():
    local('sudo ip addr del 10.20.0.1/24')
    local('sudo ip addr del 172.16.0.254/24')
    local('sudo ip addr del 172.16.1.1/24')


def setup():
    [create_brige(x) for x in (OVS_ADMIN_BR, OVS_PUBLIC_BR, OVS_PRIVATE_BR)]

    VIRTUALBOX_ADMIN_BR, VIRTUALBOX_PUBLIC_BR, VIRTUALBOX_PRIVATE_BR = find_virtual_box_bridges()

    local('sudo ip addr del 10.20.0.1/24 dev {}'.format(VIRTUALBOX_ADMIN_BR))
    local('sudo ip addr del 172.16.0.254/24 dev {}'.format(VIRTUALBOX_PUBLIC_BR))
    local('sudo ip addr del 172.16.1.1/24 dev {}'.format(VIRTUALBOX_PRIVATE_BR))

    local('sudo ip addr add 10.20.0.1/24 dev fuel_admin_br')
    local('sudo ip addr add 172.16.0.254/24 dev fuel_public_br')
    local('sudo ip addr add 172.16.1.1/24 dev fuel_private_br')

    if _fuel_master_available():
        create_and_attach_tap(tap_name('m', 1), OVS_ADMIN_BR)
        set_bridge('fuel-master', 1, tap_name('m', 1))
        create_and_attach_tap(tap_name('m', 2), OVS_PUBLIC_BR)
        set_bridge('fuel-master', 2, tap_name('m', 2))

    for slave in _slave_list():
        # ip tuntap add mode tap vnet0
        # ip link set vnet0 up
        # ovs-vsctl add-port br0 vnet0

        slave_id = 's{}'.format(slave.split('-')[2])

        create_and_attach_tap(tap_name(slave_id, 1), OVS_ADMIN_BR)
        set_bridge(slave, 1, tap_name(slave_id, 1))

        create_and_attach_tap(tap_name(slave_id, 2), OVS_PUBLIC_BR)
        set_bridge(slave, 2, tap_name(slave_id, 2))

        create_and_attach_tap(tap_name(slave_id, 3), OVS_PRIVATE_BR)
        set_bridge(slave, 3, tap_name(slave_id, 3))


def revert():

    local('sudo ip addr del 10.20.0.1/24 dev fuel_admin_br')
    local('sudo ip addr del 172.16.0.254/24 dev fuel_public_br')
    local('sudo ip addr del 172.16.1.1/24 dev fuel_private_br')

    VIRTUALBOX_ADMIN_BR, VIRTUALBOX_PUBLIC_BR, VIRTUALBOX_PRIVATE_BR = find_virtual_box_bridges()

    local('sudo ip addr add 10.20.0.1/24 dev {}'.format(VIRTUALBOX_ADMIN_BR))
    local('sudo ip addr add 172.16.0.254/24 dev {}'.format(VIRTUALBOX_PUBLIC_BR))
    local('sudo ip addr add 172.16.1.1/24 dev {}'.format(VIRTUALBOX_PRIVATE_BR))

    if _fuel_master_available():
        local('VBoxManage modifyvm fuel-master --nic1 hostonly')
        local('VBoxManage modifyvm fuel-master --hostonlyadapter1 {}'.format(VIRTUALBOX_ADMIN_BR))
        local('VBoxManage modifyvm fuel-master --nic2 hostonly')
        local('VBoxManage modifyvm fuel-master --hostonlyadapter2 {}'.format(VIRTUALBOX_PUBLIC_BR))

    for slave in _slave_list():

        local('VBoxManage modifyvm {} --nic1 hostonly'.format(slave))
        local('VBoxManage modifyvm {} --hostonlyadapter1 {}'.format(slave, VIRTUALBOX_ADMIN_BR))
        local('VBoxManage modifyvm {} --nic2 hostonly'.format(slave))
        local('VBoxManage modifyvm {} --hostonlyadapter2 {}'.format(slave, VIRTUALBOX_PUBLIC_BR))
        local('VBoxManage modifyvm {} --nic3 hostonly'.format(slave))
        local('VBoxManage modifyvm {} --hostonlyadapter3 {}'.format(slave, VIRTUALBOX_PRIVATE_BR))

        slave_id = 's{}'.format(slave.split('-')[2])
        delete_tap(tap_name(slave_id, 1), OVS_ADMIN_BR)
        delete_tap(tap_name(slave_id, 2), OVS_PUBLIC_BR)
        delete_tap(tap_name(slave_id, 3), OVS_PRIVATE_BR)

    if _fuel_master_available():
        delete_tap(tap_name('m', 1), OVS_ADMIN_BR)
        delete_tap(tap_name('m', 2), OVS_PUBLIC_BR)

    [local('sudo ovs-vsctl --if-exists del-port {} gre{}'.format(x, GRE_KEY[x])) for x in (OVS_ADMIN_BR, OVS_PUBLIC_BR, OVS_PRIVATE_BR)]
    [local('sudo ovs-vsctl --if-exists del-br {}'.format(x)) for x in (OVS_ADMIN_BR, OVS_PUBLIC_BR, OVS_PRIVATE_BR)]

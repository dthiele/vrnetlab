#!/usr/bin/env python3

import datetime
import logging
import os
import re
import signal
import subprocess
import sys

import vrnetlab


def handle_SIGCHLD(signal, frame):
    os.waitpid(-1, os.WNOHANG)


def handle_SIGTERM(signal, frame):
    sys.exit(0)


signal.signal(signal.SIGINT, handle_SIGTERM)
signal.signal(signal.SIGTERM, handle_SIGTERM)
signal.signal(signal.SIGCHLD, handle_SIGCHLD)

TRACE_LEVEL_NUM = 9
logging.addLevelName(TRACE_LEVEL_NUM, "TRACE")


def trace(self, message, *args, **kws):
    # Yes, logger takes its '*args' as 'args'.
    if self.isEnabledFor(TRACE_LEVEL_NUM):
        self._log(TRACE_LEVEL_NUM, message, args, **kws)


logging.Logger.trace = trace


class Blob_vm(vrnetlab.VM):
    def __init__(
        self,
        hostname,
        username,
        password,
        nics,
        conn_mode,
    ):
        for e in os.listdir("/images"):
            if re.search(".rootfs.ext4$", e):
                disk_image = "/images/" + e

        for e in os.listdir("/images"):
            if re.search("^Image$", e):
                kernel = "/images/" + e

        self.init2(username, password, disk_image=disk_image, kernel=kernel)

        self.num_nics = nics
        self.hostname = hostname
        self.conn_mode = conn_mode
        self.nic_type = "virtio-net-pci"

    def init2(
        self,
        username,
        password,
        disk_image="",
        kernel="",  # EDITED (ADDED)
        num=0,
        ram=256,  # EDITED
        driveif="ide",
        provision_pci_bus=True,
        cpu="cortex-a57",  # EDITED
        smp="4",  # EDITED
        mgmt_passthrough=False,
        mgmt_intf="eth0",
        mgmt_dhcp=False,
        min_dp_nics=0,
        use_scrapli=False,
        data_intf_prefix="eth",
    ):
        self.use_scrapli = use_scrapli

        # configure logging
        self.logger = logging.getLogger()

        """
        Configure Scrapli logger to only be INFO level.
        Scrapli uses 'scrapli' logger by default, and
        will write all channel i/o as DEBUG log level.
        """
        self.scrapli_logger = logging.getLogger("scrapli")

        scrapli_log_level = (
            logging.DEBUG
            if os.getenv("DEBUG_SCRAPLI", "false").lower() == "true"
            else logging.INFO
        )
        self.scrapli_logger.setLevel(scrapli_log_level)

        # username / password to configure
        self.username = username
        self.password = password

        self.num = num
        self.image = disk_image
        self.kernel = kernel

        self.running = False
        self.spins = 0
        self.p = None
        self.tn = None

        self._ram = ram
        self._cpu = cpu
        self._smp = smp
        self.mgmt_intf = os.environ.get("CLAB_MGMT_INTF", mgmt_intf)

        # various settings
        self.uuid = None
        self.fake_start_date = None
        self.nic_type = "e1000"
        self.num_nics = 0
        # number of nics that are actually *provisioned* (as in nics that will be added to container)
        self.num_provisioned_nics = int(os.environ.get("CLAB_INTFS", 0))
        # "highest" provisioned nic num -- used for making sure we can allocate nics without needing
        # to have them allocated sequential from eth1
        self.highest_provisioned_nic_num = 0

        # Whether the management interface is pass-through or host-forwarded.
        # Host-forwarded is the original vrnetlab mode where a VM gets a static IP for its management address,
        # which **does not** match the eth0 interface of a container.
        # In pass-through mode the VM container uses the same IP as the container's eth0 interface and transparently forwards traffic between the two interfaces.
        # See https://github.com/hellt/vrnetlab/issues/286
        self.mgmt_passthrough = (
            os.environ.get("CLAB_MGMT_PASSTHROUGH", "").lower() == "true"
            if os.environ.get("CLAB_MGMT_PASSTHROUGH")
            else mgmt_passthrough
        )

        # Check if CLAB_MGMT_DHCP environment variable is set
        self.mgmt_dhcp = (
            os.environ.get("CLAB_MGMT_DHCP", "").lower() == "true"
            if os.environ.get("CLAB_MGMT_DHCP")
            else mgmt_dhcp
        )

        # Check if CLAB_INTF_PREFIX environment variable is set
        self.data_intf_prefix = os.environ.get("CLAB_INTF_PREFIX", data_intf_prefix)

        # Populate management IP and gateway
        # If CLAB_MGMT_DHCP environment variable is set, we assume that a DHCP client
        # inside of the VM will take care about setting the management IP and gateway.
        if self.mgmt_passthrough:
            if self.mgmt_dhcp:
                self.mgmt_address_ipv4 = "dhcp"
                self.mgmt_address_ipv6 = "dhcp"
                self.mgmt_gw_ipv4 = "dhcp"
                self.mgmt_gw_ipv6 = "dhcp"
            else:
                self.mgmt_address_ipv4, self.mgmt_address_ipv6 = self.get_mgmt_address()
                self.mgmt_gw_ipv4, self.mgmt_gw_ipv6 = self.get_mgmt_gw()
        else:
            self.mgmt_address_ipv4 = "10.0.0.15/24"
            self.mgmt_address_ipv6 = "2001:db8::2/64"
            self.mgmt_gw_ipv4 = "10.0.0.2"
            self.mgmt_gw_ipv6 = "2001:db8::1"

        self.insuffucient_nics = False
        self.min_nics = 0
        # if an image needs minimum amount of dataplane nics to bootup, specify
        if min_dp_nics:
            self.min_nics = min_dp_nics

        # management subnet properties, defaults
        self.mgmt_subnet = "10.0.0.0/24"
        self.mgmt_host_ip = 2
        self.mgmt_guest_ip = 15

        #  Default TCP ports forwarded (TODO tune per platform):
        #  80    - http
        #  443   - https
        #  830   - netconf
        #  6030  - gnmi/gnoi arista
        #  8080  - sonic gnmi/gnoi, other http apis
        #  9339  - iana gnmi/gnoi
        #  32767 - gnmi/gnoi juniper
        #  50051 - cisco nx-os gnmi/gnoi
        #  57400 - nokia gnmi/gnoi
        self.mgmt_tcp_ports = [80, 443, 830, 6030, 8080, 9339, 32767, 50051, 57400]

        # we setup pci bus by default
        self.provision_pci_bus = provision_pci_bus
        self.nics_per_pci_bus = 26  # tested to work with XRv
        self.smbios = []

        self.start_nic_eth_idx = 1

        # wait_pattern is the pattern we wait on the serial connection when pushing config commands
        self.wait_pattern = "#"

        self.qemu_args = [
            "qemu-system-aarch64",
            "-machine",
            "virt",
            "-m",  # memory
            str(self.ram),
            "-cpu",  # cpu type
            self.cpu,
            "-smp",
            self.smp,  # cpu core configuration
            "-monitor",
            f"tcp:0.0.0.0:40{self.num:02d},server,nowait",
            "-serial",
            f"telnet:0.0.0.0:50{self.num:02d},server,nowait",
            "-nographic",
            "-object",
            "rng-random,filename=/dev/urandom,id=rng0",
            "-device",
            "virtio-rng-pci,rng=rng0",
            "-drive",
            f"id=disk0,file={self.image},if=none,format=raw",
            "-device",
            "virtio-blk-pci,drive=disk0",
            "-kernel",
            self.kernel,
            "-append",
            f"'root=/dev/vda rw mem={self.ram}M ip=10.0.0.15::10.0.0.2:255.255.255.0::eth0:off:8.8.8.8 console=ttyAMA0 net.ifnames=0'",
        ]

        # add additional qemu args if they were provided
        if self.qemu_additional_args:
            self.qemu_args.extend(self.qemu_additional_args)

        # EDITED: Disable KVM. Does not seem to work for cross architecture emulation.
        # TODO: Add check if emuated CPU is "KVM-compatible" with host CPU.
        # enable hardware assist if KVM is available
        # if os.path.exists("/dev/kvm"):
        #    self.qemu_args.insert(1, "-enable-kvm")

    def bootstrap_spin(self):
        """This function should be called periodically to do work."""

        if self.spins > 6000:
            # too many spins with no result ->  give up
            self.logger.debug("Too many spins -> give up")
            self.stop()
            self.start()
            return

        (ridx, match, res) = self.tn.expect([b"login: "], 1)
        if match:  # got a match!
            if ridx == 0:  # login
                self.logger.debug("matched, login: ")
                self.wait_write("", wait=None)

                self.running = True
                # close telnet connection
                self.tn.close()
                # startup time?
                startup_time = datetime.datetime.now() - self.start_time
                self.logger.info("Startup complete in: %s", startup_time)
                return

        # no match, if we saw some output from the router it's probably
        # booting, so let's give it some more time
        if res != b"":
            self.logger.trace("OUTPUT: %s" % res.decode())
            # reset spins if we saw some output
            self.spins = 0

        self.spins += 1

        return

    def gen_mgmt(self):
        """
        Augment the parent class function to change the PCI bus
        """
        # call parent function to generate the mgmt interface
        res = super(Blob_vm, self).gen_mgmt()

        # we need to place mgmt interface on the same bus with other interfaces in Blob,
        # to get nice (predictable) interface names
        if "bus=pci.1" not in res[-3]:
            res[-3] = res[-3] + ",bus=pci.1" + ",addr=1"
        return res


class Blob(vrnetlab.VR):
    def __init__(self, hostname, username, password, nics, conn_mode):
        super(Blob, self).__init__(username, password)
        self.vms = [Blob_vm(hostname, username, password, nics, conn_mode)]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="")
    parser.add_argument(
        "--trace", action="store_true", help="enable trace level logging"
    )
    parser.add_argument("--username", default="sysadmin", help="Username")
    parser.add_argument("--password", default="sysadmin", help="Password")
    parser.add_argument("--hostname", default="ubuntu", help="VM Hostname")
    parser.add_argument("--nics", type=int, default=16, help="Number of NICS")
    parser.add_argument(
        "--connection-mode",
        default="tc",
        help="Connection mode to use in the datapath",
    )
    args = parser.parse_args()

    LOG_FORMAT = "%(asctime)s: %(module)-10s %(levelname)-8s %(message)s"
    logging.basicConfig(format=LOG_FORMAT)
    logger = logging.getLogger()

    logger.setLevel(logging.DEBUG)
    if args.trace:
        logger.setLevel(1)

    vr = Blob(
        args.hostname,
        args.username,
        args.password,
        args.nics,
        args.connection_mode,
    )
    vr.start()

import wexpect
import os
import time

VSPHERE_WITH_TANZU_CONTROL_PLANE_IP='172.16.21.129'
VSPHERE_WITH_TANZU_USERNAME='administrator@corp.local'
VSPHERE_WITH_TANZU_PASSWORD='VMware1!'

cmd = wexpect.spawn('cmd.exe')
cmd.expect('>')
cmd.sendline(f"kubectl vsphere login --vsphere-username {VSPHERE_WITH_TANZU_USERNAME} --server={VSPHERE_WITH_TANZU_CONTROL_PLANE_IP} --insecure-skip-tls-verify")

cmd.expect('Password')
cmd.sendline(VSPHERE_WITH_TANZU_PASSWORD)

cmd.expect('contexts')
cmd.sendline(f"kubectl config use-context {VSPHERE_WITH_TANZU_CONTROL_PLANE_IP}")

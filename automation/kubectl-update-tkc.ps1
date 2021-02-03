Split-path -Parent $MyInvocation.MyCommand.Definition | Set-Location

# Wait until it is applied
Do {
    kubectl apply -f .\tf-runtime.yaml
    if ($LastExitCode -ne 0) {
        python kubectl-vsphere-login.py
        Continue
    }
    Start-Sleep -Seconds 20
    $tkc = kubectl get tkc/tf-runtime -n hol-tf-service -o json | ConvertFrom-Json
    Write-Output ("Worker Nodes: " + $tkc.spec.topology.workers.count)
} While ($tkc.spec.topology.workers.count -lt 1)

# Wait until 1 worker node is ready
Do {
    Start-Sleep -Seconds 20
    $tkc = kubectl get tkc/tf-runtime -n hol-tf-service -o json | ConvertFrom-Json
    if ($LastExitCode -ne 0) {
        python kubectl-vsphere-login.py
        Continue
    }
    $workernodes = $tkc.status.nodeStatus | Get-Member | ForEach-Object { If ($_.Name -like "*workers*") { @{$_.Name = $tkc.status.nodeStatus.($_.Name) } } }
    $workernodes | Format-Table -HideTableHeaders -AutoSize | Out-String
} 
While (-Not $workernodes.Values.Contains("ready") -or $workernodes.Values.Contains("notready"))


# Get worker node connection information
$tkc = $null
Do {
    Write-Output "Getting Worker Node info"
    $tkc = kubectl get tkc/tf-runtime -n hol-tf-service -o json | ConvertFrom-Json
    if ($LastExitCode -ne 0) {
        python kubectl-vsphere-login.py
        Continue
    }
}
While (($tkc.status.vmStatus | Get-Member |  Where-Object { $_.Name -like "*workers*" }).Count -lt 1)

$workerName = ($tkc.status.vmStatus | Get-Member |  Where-Object { $_.Name -like "*workers*" })[0].Name
$workerPasswordBase64 = kubectl get secret/tf-runtime-ssh-password -n hol-tf-service -o jsonpath='{.data.ssh-passwordkey}'
$workerPassword = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($workerPasswordBase64))

try {
    Connect-VIserver "vcsa-01a.corp.local" -username "administrator@corp.local" -password "VMware1!" -ErrorAction Stop
}
catch {
    Write-Host -ForegroundColor Red "ERROR: Unable to connect to vCenter"
    Return
}

$esxHost = (Get-VM -Name $workerName -Server "vcsa-01a.corp.local").VMHost.Name

Disconnect-VIServer * -Confirm:$false | Out-Null


# Connect to ESXi and perform customization
Connect-VIserver $esxHost -username root -password "VMware1!" -ErrorAction Stop
$workerVm = Get-VM -Name $workerName -Server $esxHost
Invoke-VMScript -VM $workerVm  -GuestUser "vmware-system-user" -GuestPassword $workerPassword -ScriptText "sudo sed -ir '/\[Network\]/a Domains=corp.local' /etc/systemd/network/10-eth0.network"
Invoke-VMScript -VM $workerVm  -GuestUser "vmware-system-user" -GuestPassword $workerPassword -ScriptText "sudo systemctl restart systemd-networkd systemd-resolved"
Copy-VMGuestFile -VM $workerVm  -GuestUser "vmware-system-user" -GuestPassword $workerPassword -LocalToGuest -Source C:\hol\SSL\CA-Certificate.cer -Destination "/home/vmware-system-user/ca.crt"
Invoke-VMScript -VM $workerVm  -GuestUser "vmware-system-user" -GuestPassword $workerPassword -ScriptText "cat /home/vmware-system-user/ca.crt | sudo tee -a /etc/pki/tls/certs/ca-bundle.crt"

Disconnect-VIServer * -Confirm:$false | Out-Null
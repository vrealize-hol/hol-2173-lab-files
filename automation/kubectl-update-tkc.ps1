Split-path -Parent $MyInvocation.MyCommand.Definition | Set-Location

# Wait until it is applied
Do {
    kubectl apply -f .\tf-runtime.yaml
    Start-Sleep -Seconds 20
    $tkc = kubectl get tkc/tf-runtime -n hol-tf-service -o json | ConvertFrom-Json
    Write-Output ("Worker Nodes: " + $tkc.spec.topology.workers.count)

} While ($tkc.spec.topology.workers.count -lt 1)

# Wait until 1 worker node is ready
Do {
    Start-Sleep -Seconds 20
    $tkc = kubectl get tkc/tf-runtime -n hol-tf-service -o json | ConvertFrom-Json
    $workernodes = $tkc.status.nodeStatus | Get-Member | ForEach-Object { If ($_.Name -like "*workers*") { @{$_.Name = $tkc.status.nodeStatus.($_.Name) } } }
    $workernodes | Format-Table -HideTableHeaders -AutoSize | Out-String
} 
While (-Not $workernodes.Values.Contains("ready"))

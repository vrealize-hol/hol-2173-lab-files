@echo off
cd %~dp0

python kubectl-vsphere-login.py
kubectl config get-contexts

powershell -File .\kubectl-update-tkc.ps1

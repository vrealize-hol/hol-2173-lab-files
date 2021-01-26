@echo off
cd %~dp0

python kubectl-vsphere-login.py
kubectl apply -f tf-runtime.yaml

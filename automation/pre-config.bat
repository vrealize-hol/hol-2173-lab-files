@echo off
cd %~dp0

python kubectl-vsphere-login.py

kubectl config get-contexts
kubectl get tkc/tf-runtime -n hol-tf-service -o=jsonpath={.spec.topology.workers.count}

kubectl apply -f tf-runtime.yaml

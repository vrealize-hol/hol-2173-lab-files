import urllib3
import sys
import re
import subprocess
from time import strftime, sleep
import calendar
import datetime
from random import seed, randint
from boto3.dynamodb.conditions import Key, Attr
import boto3
import traceback
import os
import time
import requests
import json
urllib3.disable_warnings()

####### I M P O R T A N T #######
# If you are deploying this vPod dircetly in OneCloud and not through the Hands On Lab portal,
# you must uncomment the following lines and supply your own set of AWS and Azure keys
#################################
# awsid = "put your AWS access key here"
# awssec = "put your AWS secret hey here"
# azsub = "put your azure subscription id here"
# azten = "put your azure tenant id here"
# azappid = "put your azure application id here"
# azappkey = "put your azure application key here"

# also change the "local_creds" value below to True
local_creds = False

debug = True

github_key = os.getenv('github_key')
slack_api_key = 'T024JFTN4/B0150SYEHFE/zNcnyZqWvUcEtaqyiRlLj86O'

vra_fqdn = "vr-automation.corp.local"
api_url_base = "https://" + vra_fqdn + "/"
apiVersion = "2019-01-15"

gitlab_api_url_base = "http://gitlab.corp.local/api/v4/"
gitlab_token_suffix = "?private_token=xCfcjUWxdVN7WxbUAAva"
gitlab_header = {'Content-Type': 'application/json'}

# set internet proxy for for communication out of the vPod
proxies = {
    "http": "http://192.168.110.1:3128",
    "https": "https://192.168.110.1:3128"
}

def get_vlp_urn():
    # determine current pod's URN (unique ID) using Main Console guestinfo
    # this uses a VLP-set property named "vlp_vapp_urn" and will only work for a pod deployed by VLP

    tools_location = 'C:\\Program Files\\VMware\\VMware Tools\\vmtoolsd.exe'
    command = '--cmd "info-get guestinfo.ovfenv"'
    full_command = tools_location + " " + command

    if os.path.isfile(tools_location):
        response = subprocess.run(full_command, stdout=subprocess.PIPE)
        byte_response = response.stdout
        txt_response = byte_response.decode("utf-8")

        try:
            urn = re.search('urn:vcloud:vapp:(.+?)"/>', txt_response).group(1)
        except:
            return('No urn parameter found')

        if len(urn) > 0:
            return urn
        else:
            return('No urn value found')

    else:
        return('Error: VMware tools not found')


def get_available_pod():
    # this function checks the dynamoDB to see if there are any available AWS and Azure key sets to configure the cloud accounts

    dynamodb = boto3.resource(
        'dynamodb', aws_access_key_id=d_id, aws_secret_access_key=d_sec, region_name=d_reg)
    table = dynamodb.Table('HOL-keys')

    response = table.scan(
        FilterExpression=Attr('reserved').eq(0),
        ProjectionExpression="pod, in_use"
    )
    pods = response['Items']
    # the number of pods not reserved
    num_not_reserved = len(pods)
    available_pods = 0  # set counter to zero
    pod_array = []
    for i in pods:
        if i['in_use'] == 0:  # pod is available
            available_pods += 1  # increment counter
            pod_array.append(i['pod'])

    if available_pods == 0:  # all credentials are assigned
        # get the oldest credentials and re-use those
        response = table.scan(
            FilterExpression=Attr('check_out_epoch').gt(0),
            ProjectionExpression="pod, check_out_epoch"
        )
        pods = response['Items']
        oldest = pods[0]['check_out_epoch']
        pod = pods[0]['pod']
        for i in pods:
            if i['check_out_epoch'] < oldest:
                pod = i['pod']
                oldest = i['check_out_epoch']
    else:
        # get random pod from those available
        dt = datetime.datetime.microsecond
        seed(dt)
        rand_int = randint(0, available_pods-1)
        pod = pod_array[rand_int]
    return(pod, num_not_reserved, available_pods)


def get_creds(cred_set, vlp_urn_id):

    dynamodb = boto3.resource(
        'dynamodb', aws_access_key_id=d_id, aws_secret_access_key=d_sec, region_name=d_reg)
    table = dynamodb.Table('HOL-keys')

    a = time.gmtime()  # gmt in structured format
    epoch_time = calendar.timegm(a)  # convert to epoc
    human_time = strftime("%m-%d-%Y %H:%M", a)

    # get the key set
    response = table.get_item(
        Key={
            'pod': cred_set
        }
    )
    results = response['Item']

    # write some items
    response = table.update_item(
        Key={
            'pod': cred_set
        },
        UpdateExpression="set in_use = :inuse, vlp_urn=:vlp, check_out_epoch=:out, check_out_human=:hout",
        ExpressionAttributeValues={
            ':inuse': 1,
            ':vlp': vlp_urn_id,
            ':out': epoch_time,
            ':hout': human_time
        },
        ReturnValues="UPDATED_NEW"
    )

    return(results)

def log(msg):
    if debug:
        sys.stdout.write(msg + '\n')
    file = open("C:\\hol\\vraConfig.log", "a")
    file.write(msg + '\n')
    file.close()


def send_slack_notification(payload):
    slack_url = 'https://hooks.slack.com/services/'
    post_url = slack_url + slack_api_key
    requests.post(url=post_url, proxies=proxies, json=payload)
    return()


def extract_values(obj, key):
    """Pull all values of specified key from nested JSON."""
    arr = []

    def extract(obj, arr, key):
        """Recursively search for values of key in JSON tree."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    extract(v, arr, key)
                elif k == key:
                    arr.append(v)
        elif isinstance(obj, list):
            for item in obj:
                extract(item, arr, key)
        return arr
    results = extract(obj, arr, key)
    return results


def get_token(user_name, pass_word):
    api_url = '{0}csp/gateway/am/api/login?access_token'.format(api_url_base)
    data = {
        "username": user_name,
        "password": pass_word
    }
    response = requests.post(api_url, headers=headers,
                             data=json.dumps(data), verify=False)
    if response.status_code == 200:
        json_data = response.json()
        key = json_data['access_token']
        return key
    else:
        return('not ready')


def get_projids():
    api_url = '{0}iaas/api/projects'.format(api_url_base)
    response = requests.get(api_url, headers=headers1, verify=False)
    if response.status_code == 200:
        json_data = response.json()
        proj_id = extract_values(json_data, 'id')
        return proj_id
    else:
        log('- Failed to get the project IDs')
        return None


def get_right_projid(projid):
    api_url = '{0}iaas/api/projects/{1}'.format(api_url_base, projid)
    response = requests.get(api_url, headers=headers1, verify=False)
    if response.status_code == 200:
        json_data = response.json()
        proj_name = extract_values(json_data, 'name')
        for x in proj_name:
            if x == 'HOL Project':
                return projid
    else:
        log('- Failed to get the right project ID')
        return None


def get_right_projid_rp(projid):
    api_url = '{0}iaas/api/projects/{1}'.format(api_url_base, projid)
    response = requests.get(api_url, headers=headers1, verify=False)
    if response.status_code == 200:
        json_data = response.json()
        proj_name = extract_values(json_data, 'name')
        for x in proj_name:
            if x == 'Rainpole Project':
                return projid
    else:
        log('- Failed to get the right project ID')
        return None


def create_labauto_project():
    api_url = '{0}iaas/api/projects'.format(api_url_base)
    data = {
        "name": "Lab Automation Project",
        "administrators": [
                    {
                        "email": "holadmin"
                    }
                ],
        "sharedResources": "true"
    }
    response = requests.post(api_url, headers=headers1,
                             data=json.dumps(data), verify=False)
    if response.status_code == 201:
        log('- Successfully created the Lab Automation project')
    else:
        log('- Failed to create the Lab Automation project')


def add_github_integration():
    # adds GitHub as an integration endpoint
    api_url = '{0}provisioning/uerp/provisioning/mgmt/endpoints?external'.format(
        api_url_base)
    data = {
        "endpointProperties": {
            "url": "https://api.github.com",
            "privateKey": github_key,
            "dcId": "onprem"
        },
        "customProperties": {
            "isExternal": "true"
        },
        "endpointType": "com.github.saas",
        "associatedEndpointLinks": [],
        "name": "HOL Lab Files",
        "tagLinks": []
    }
    response = requests.post(api_url, headers=headers1,
                             data=json.dumps(data), verify=False)
    if response.status_code == 200:
        json_data = response.json()
        integrationSelfLink = json_data["documentSelfLink"]
        integrationId = re.findall(
            r"([0-9A-F]{8}[-]?(?:[0-9A-F]{4}[-]?){3}[0-9A-F]{12})", integrationSelfLink, re.IGNORECASE)[0]
        log('- Successfully added GitHub integration endpoint')
        return(integrationId)
    else:
        log('- Failed to add GitHub integration endpoint')


def configure_github(projId, gitId):
    # adds GitHub blueprint integration with the HOL Project
    api_url = '{0}content/api/sources'.format(api_url_base)
    data = {
        "name": "GitHub CS",
        "typeId": "com.github",
        "syncEnabled": "true",
        "projectId": projId,
        "config": {
            "integrationId": gitId,
            "repository": "vrealize-hol/hol-2121-lab-files",
            "path": "blueprints",
            "branch": "sandbox",
            "contentType": "blueprint"
        }
    }
    response = requests.post(api_url, headers=headers1,
                             data=json.dumps(data), verify=False)
    if response.status_code == 201:
        log('- Successfully added blueprint repo to project')
    else:
        log('- Failed to add the blueprint repo to project')


def get_pricing_card():
    api_url = '{0}price/api/private/pricing-cards'.format(api_url_base)
    response = requests.get(api_url, headers=headers1, verify=False)
    if response.status_code == 200:
        json_data = response.json()
        content = json_data["content"]
        count = json_data["totalElements"]
        for x in range(count):
            # Looking to match the Default pricing card
            if 'Default Pricing' in content[x]["name"]:
                id = (content[x]["id"])
                return id
    else:
        log('- Failed to get default pricing card')
        return None

def sync_price():
    url = f"{api_url_base}price/api/sync-price-task"
    response = requests.request(
        "POST", url, headers=headers1, data=json.dumps({}), verify=False)
    if response.status_code == 202:
        log('- Successfully synced prices')
    else:
        log(f'- Failed to sync prices ({response.status_code})')

def modify_pricing_card(cardid):
    # modifies the Default Pricing card
    api_url = '{0}price/api/private/pricing-cards/{1}'.format(
        api_url_base, cardid)
    data = {
        "name": "HOL Pricing Card",
        "description": "Sets pricing rates for vSphere VMs",
        "meteringItems": [
            {
                "itemName": "vcpu",
                "metering": {
                    "baseRate": 29,
                    "chargePeriod": "MONTHLY",
                    "chargeOnPowerState": "ALWAYS",
                    "chargeBasedOn": "USAGE"
                }
            },
            {
                "itemName": "memory",
                "metering": {
                    "baseRate": 85,
                    "chargePeriod": "MONTHLY",
                    "chargeOnPowerState": "ALWAYS",
                    "chargeBasedOn": "USAGE",
                    "unit": "gb"
                },
            },
            {
                "itemName": "storage",
                "metering": {
                    "baseRate": 0.14,
                    "chargePeriod": "MONTHLY",
                    "chargeOnPowerState": "ALWAYS",
                    "chargeBasedOn": "USAGE",
                    "unit": "gb"
                }
            }
        ],
        "chargeModel": "PAY_AS_YOU_GO"
    }
    response = requests.put(api_url, headers=headers1,
                            data=json.dumps(data), verify=False)
    if response.status_code == 200:
        log('- Successfully modified the pricing card')
    else:
        log('- Failed to modify the pricing card')


def get_blueprint_id(bpName):
    api_url = '{0}blueprint/api/blueprints'.format(api_url_base)
    response = requests.get(api_url, headers=headers1, verify=False)
    if response.status_code == 200:
        json_data = response.json()
        content = json_data["content"]
        count = json_data["totalElements"]
        for x in range(count):
            if bpName in content[x]["name"]:  # Looking to match the blueprint name
                bp_id = (content[x]["id"])
                return bp_id
    else:
        log('- Failed to get the blueprint ID for ' + bpName)
        return None


def release_blueprint(bpid, ver):
    api_url = '{0}blueprint/api/blueprints/{1}/versions/{2}/actions/release'.format(
        api_url_base, bpid, ver)
    data = {}
    response = requests.post(api_url, headers=headers1,
                             data=json.dumps(data), verify=False)
    if response.status_code == 200:
        log('- Successfully released the blueprint')
    else:
        log('- Failed to releasea the blueprint')


def add_bp_cat_source(projid):
    # adds blueprints from 'projid' project as a content source
    api_url = '{0}catalog/api/admin/sources'.format(api_url_base)
    data = {
        "name": "HOL Project Blueprints",
        "typeId": "com.vmw.blueprint",
        "description": "Released blueprints in the HOL Project",
        "config": {"sourceProjectId": projid},
        "projectId": projid
    }
    response = requests.post(api_url, headers=headers1,
                             data=json.dumps(data), verify=False)
    if response.status_code == 201:
        json_data = response.json()
        sourceId = json_data["id"]
        log('- Successfully added blueprints as a catalog source')
        return sourceId
    else:
        log('- Failed to add blueprints as a catalog source')
        return None


def share_bps(source, project):
    # shares blueprint content (source) from 'projid' project to the catalog
    api_url = '{0}catalog/api/admin/entitlements'.format(api_url_base)
    data = {
        "definition": {"type": "CatalogSourceIdentifier", "id": source},
        "projectId": project
    }
    response = requests.post(api_url, headers=headers1,
                             data=json.dumps(data), verify=False)
    if response.status_code == 201:
        log('- Successfully added blueprint catalog entitlement')
    else:
        log('- Failed to add blueprint catalog entitlement')
        return None


def get_cat_id(item_name):
    api_url = '{0}catalog/api/items'.format(api_url_base)
    response = requests.get(api_url, headers=headers1, verify=False)
    if response.status_code == 200:
        json_data = response.json()
        content = json_data["content"]
        count = json_data["totalElements"]
        for x in range(count):
            # Looking to match the named catalog item
            if item_name in content[x]["name"]:
                cat_id = (content[x]["id"])
                return cat_id
    else:
        log('- Failed to get the blueprint ID')
        return None


def deploy_cat_item(catId, project):
    # shares blueprint content (source) from 'projid' project to the catalog
    api_url = '{0}catalog/api/items/{1}/request'.format(api_url_base, catId)
    data = {
        "deploymentName": "vSphere Ubuntu",
        "projectId": project,
        "version": "1",
        "reason": "Deployment of vSphere vm from blueprint",
        "inputs": {}
    }
    response = requests.post(api_url, headers=headers1,
                             data=json.dumps(data), verify=False)
    if response.status_code == 200:
        log('- Successfully deployed the catalog item')
    else:
        log('- Failed to deploy the catalog item')


def check_for_assigned(vlpurn):
    # this function checks the dynamoDB to see if this pod urn already has a credential set assigned

    dynamodb = boto3.resource(
        'dynamodb', aws_access_key_id=d_id, aws_secret_access_key=d_sec, region_name=d_reg)
    table = dynamodb.Table('HOL-keys')

    response = table.scan(
        FilterExpression="attribute_exists(vlp_urn)",
        ProjectionExpression="pod, vlp_urn"
    )
    urns = response['Items']
    urn_assigned = False
    for i in urns:
        if i['vlp_urn'] == vlpurn:  # This URN already has a key assigned
            urn_assigned = True

    return(urn_assigned)


def getOrg(headers):
    url = f"{api_url_base}csp/gateway/am/api/loggedin/user/orgs"
    response = requests.request(
        "GET", url, headers=headers, verify=False)
    return response.json()['items'][0]['id']


def getEndpoints(headers):
    url = f"{api_url_base}provisioning/uerp/provisioning/mgmt/endpoints?expand"
    response = requests.request("GET", url, headers=headers, verify=False)
    if response.status_code == 200:
        log("- Successfully retrieved endpoint list")    
        endpointList = {}
        for endpoint_link in response.json()['documentLinks']:
            endpoint = response.json()['documents'][endpoint_link]
            endpointList[endpoint['endpointType']] = endpoint['documentSelfLink']
        return endpointList


def is_configured():
    # checks to see if vRA is already configured
    api_url = '{0}iaas/api/cloud-accounts'.format(api_url_base)
    response = requests.get(api_url, headers=headers1, verify=False)
    if response.status_code == 200:
        json_data = response.json()
        caTypes = extract_values(json_data, 'cloudAccountType')
        for x in caTypes:
            if 'azure' in x: 
                return True
        return False
    else:
        log('Could not get cloud accounts')


def get_gitlab_projects():
    # returns an array containing all of the project ids
    api_url = '{0}projects{1}'.format(gitlab_api_url_base, gitlab_token_suffix)
    response = requests.get(api_url, headers=gitlab_header, verify=False)
    if response.status_code == 200:
        json_data = response.json()
        for project in json_data:
            if 'dev' in project['name']:        # looking for the 'dev' project
                return project['id']
        else:
            log('- Did not find the dev gitlab project')
    else:
        log('- Failed to get gitlab projects')


def update_git_proj(projId):
    # sets the visibility of the passed project ID to public
    api_url = '{0}projects/{1}{2}'.format(gitlab_api_url_base, projId, gitlab_token_suffix)
    data = {
        "visibility": "public"
    }
    response = requests.put(api_url, headers=gitlab_header, data=json.dumps(data), verify=False)
    if response.status_code == 200:
        log('- Updated the gitlab project')
    else:
        log('- Failed to update the gitlab project')


##### MAIN #####

headers = {'Content-Type': 'application/json'}

if local_creds != True:
    log('Getting ddb creds from router')
    try:
        keyfile = subprocess.check_output('plink -ssh router -l holuser -pw VMware1! cat mainconsole/ddb.json')
    except:
        log('Unable to get ddb creds from router')
        log('... exiting')
        vlpurn = get_vlp_urn()
        payload = {"text": f"*WARNING - Could not get ddb creds for the pod with VLP URN: {vlpurn}*"}
        send_slack_notification(payload)
        sys.exit(0)
    log('Got ddb creds from router')
    json_data = json.loads(keyfile)
    d_id = json_data['d_id']
    d_sec = json_data['d_sec']
    d_reg = json_data['d_reg']
    subprocess.call('plink -ssh router -l holuser -pw VMware1! rm mainconsole/ddb.json')
    log('Removed ddb creds from router')

###########################################
# API calls below as holadmin
###########################################
access_key = get_token("holadmin", "VMware1!")

# find out if vRA is ready. if not ready we need to exit or the configuration will fail
if access_key == 'not ready':  # we are not even getting an auth token from vRA yet
    log('\n\n\nvRA is not yet ready in this Hands On Lab pod - no access token yet')
    log('Wait for the lab status to be *Ready* and then run this script again')
    sys.stdout.write('vRA did not return an access key')
    sys.exit(1)

headers1 = {'Content-Type': 'application/json',
            'Authorization': 'Bearer {0}'.format(access_key)}
headers2 = {'Content-Type': 'application/x-yaml',
            'Authorization': 'Bearer {0}'.format(access_key)}

# check to see if vRA is already configured and exit if it is
if is_configured():
    log('vRA is already configured')
    log('... exiting')
    sys.stdout.write('vRA is already configured')
    sys.exit(1)

# check to see if this vPod was deployed by VLP (is it an active Hands on Lab?)
result = get_vlp_urn()
log('VLP URN = ' + result)
hol = True  # assume it is - the next step will change it if not
if 'No urn' in result:
    # this pod was not deployed by VLP = keys must be defined at top of this file
    hol = False
    log('\n\nThis pod was not deployed as a Hands On Lab')
    try:
        # test to see if public cloud keys are included at start of script
        msg = awsid
    except:
        log('\n\n* * * *   I M P O R T A N T   * * * * *\n')
        log('You must provide AWS and Azure key sets at the top of the "C:\\hol-2121-lab-files\\automation\\2121-base-config.py" script')
        log('Uncomment the keys, replace with your own and run the configuration script again')
        sys.exit()
else:
    vlp = result

# if this pod is running as a Hands On Lab
if hol:
    log('Pod is running in VLP')

    # find out if this pod already has credentials assigned
    credentials_used = check_for_assigned(vlp)
    if credentials_used:
        log('\n\n\nThis Hands On Lab pod already has credentials assigned')
        log('You do not need to run this script again')
        sys.exit()

    assigned_pod = get_available_pod()  # find an available credential set
    cred_set = assigned_pod[0]
    unreserved_count = assigned_pod[1]
    available_count = assigned_pod[2]
    keys = get_creds(cred_set, vlp)
    log(f'cred set: {cred_set}')
    awsid = keys['aws_access_key']
    awssec = keys['aws_secret_key']
    azsub = keys['azure_subscription_id']
    azten = keys['azure_tenant_id']
    azappkey = keys['azure_application_key']
    azappid = keys['azure_application_id']

    if available_count > 0:
        available_count = available_count-1

    # build and send Slack notification
    info = ""
    info += (f'*Credential set {cred_set} was assigned to the {vlp} VLP urn* \n')
    info += (f'- There are {available_count} sets remaining out of {unreserved_count} available \n')
    payload = {"text": info}
    send_slack_notification(payload)


log('Creating projects')
#create_labauto_project()

log('Creating GitHub blueprint repo integration')
# gitId = add_github_integration()
# configure_github(hol_project, gitId)

log('Waiting for git repo to sync')
# time.sleep(20)

log('Configuring pricing')
# pricing_card_id = get_pricing_card()
# modify_pricing_card(pricing_card_id)
# sync_price()

log('Adding blueprints to the catalog')
# blueprint_id = get_blueprint_id('Ubuntu 18')
# release_blueprint(blueprint_id, 1)
# bp_source = add_bp_cat_source(hol_project)
# share_bps(bp_source, hol_project)

##########################################
# API calls below as holuser
##########################################
# access_key = get_token("holuser", "VMware1!")
# headers1 = {'Content-Type': 'application/json',
#             'Authorization': 'Bearer {0}'.format(access_key)}

# time.sleep(30)
# log('Deploying vSphere VM')
# catalog_item = get_cat_id('Ubuntu 18')
# deploy_cat_item(catalog_item, hol_project)

##########################################
# Configure GitLab Project
##########################################
log('Configuring GitLab')
# git_proj_id = get_gitlab_projects()
# update_git_proj(git_proj_id)

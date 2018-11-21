#!/usr/bin/env python3

# Orginally written in PowerShell by Brian Holiday
# Modified and re-written (aka mangled) in Python by Christopher van de Sande
# Requires Python 3.x, Requests module and awscli (pip3 install requests awscli)
# V2 -- 26.08.2017 -- Re-written to support multiple threads cross platform
# V3 -- 21.11.2018 -- Cloudgateway was returning no values, so keep hitting it 
# with a while loop until it bleeds

# This script supports username and paswword as arguments, otherwise it detects
# or simply prompts the user for what it needs
# format is 'getCreds.py DOMAIN Username Password'
# e.g getCreds.py EUROPE cvandesande MyPassWord
# 

import getpass
import multiprocessing.pool
import os
import platform
import requests
import sys


# Main variables set these as you see fit
accToPull = 'Ops'
rolesUrl = 'https://cloudgateway.pgi.com/api/aws/roles'
sessionsUrl = 'https://cloudgateway.pgi.com/api/aws/sessions'
hours = '36' # Max is 36
reason = 'Daily backup of keys'
setKeyCmd = 'aws configure set aws_access_key_id '
setSecretCmd = 'aws configure set aws_secret_access_key ' 
headers = {'CloudGateway-Username': '',\
 'CloudGateway-Password': '',\
 'Accept': 'application/vnd.cloudgateway.v1+json',\
 'Content-Type': 'application/json'}

sys.tracebacklimit = None # Reduces ugliness of errors

 
# Check for awscli installation
def awsCheck():
  print('Checking for existence of awscli...')
  awsVersion = os.system('aws --version')
  print()
  if not awsVersion == 0:
    raise ValueError('Error running aws, make sure you have awscli installed')


# Fancy function to gather user credentials
def userCreds():
  if len(sys.argv) == 4:
    userName = sys.argv[1] + '\\' + sys.argv[2]
    passWd = sys.argv[3]
  elif platform.system() == 'Windows':
    print('Please type your DOMAIN\\Username or enter to use logged in user')
    userName = os.environ['userdomain'] + '\\' + getpass.getuser()
    userName = input('Username ' + '[' + userName + ']: ') or userName
    passWd = getpass.getpass(prompt='Enter password: ', stream=None)
  else:
    print()
    userName = input('Please type your DOMAIN\\UserName: ')
    passWd = getpass.getpass(prompt='Enter password: ', stream=None)
  uCreds = (userName, passWd)
  return uCreds

# Update headers with user credentials
def setHeaders(user, password):
  global headers
  headers['CloudGateway-Username'] = user
  headers['CloudGateway-Password'] = password  

# Fetch list of roles from CG
def getRoles():
  try:
    roles = requests.get(rolesUrl, headers=headers).json()
  except requests.exceptions.Timeout as tmo:
    print('Timeout connecting to Cloud Gateway')
  except requests.exceptions.ConnectionError:
    print('Error during connection attempt, check rolesUrl')
  except requests.exceptions.TooManyRedirects:
    print('Too many redirects, check rolesUrl')
  except requests.exceptions.RequestException as e:
    print(e)
  if 'Authentication failure' in roles['errors']:
    raise ValueError('Invalid username or password')
  return roles


# Function to retrieve aws credentials (slow)
def reqCreds(account):
  awsCreds = {}
  body = {'duration_hours': hours, 'role_id': account, 'reason': reason}
  try:
    r = requests.post(sessionsUrl, headers=headers, json=body).json()
  except requests.exceptions.Timeout:
    print('Timeout connecting to Cloud Gateway')
  except requests.exceptions.ConnectionError:
    print('Error during connection attempt, check sessionsUrl')
  except requests.exceptions.TooManyRedirects:
    print('Too many redirects, check sessionsUrl')
  except requests.exceptions.RequestException as e:
    print(e)	
  awsCreds[account] = r['session']['credentials']
  while awsCreds.get(account) is None:
    print('Got nothing from ' + account + ' Retrying...')
    r = requests.post(sessionsUrl, headers=headers, json=body).json()
    awsCreds[account] = r['session']['credentials']
  print('\033[92m'\
  + 'Successfully retrieved '\
  +  accToPull\
  + ' keys for '\
  + str(account)\
  + '\x1b[0m')
  return awsCreds


# Run aws configure for account, key, secret
def setCreds(account, key, secret):
  os.system(setKeyCmd\
  + str(key)\
  + ' --profile '\
  + str(account))
  os.system(setSecretCmd\
  + str(secret)\
  + ' --profile '\
  + str(account))

# Main function, calls other functions, sorts values for next call
def main():
  awsCheck()
  uCreds = userCreds()
  setHeaders(uCreds[0], uCreds[1])
  print('Connecting to CloudGateway as ' + uCreds[0] + ' please stand by...')
  roles = getRoles()
  accounts = [i['id'] for i in roles['roles'] if accToPull in i['name']] # Yay Python list compression
  if len(accounts) == 0:
    raise ValueError('Could not find any accounts matching ' + '"' + accToPull + '"')
  pool = multiprocessing.pool.ThreadPool(len(accounts)) # Initialize x threads. 1 per account, might be dangerous
  awsCredList = pool.map(reqCreds, accounts)
  pool.close()
  pool.join()
  # Back to single threaded mode to configure awscli serially
  for d in awsCredList:
    for id in d:
        setCreds(id, d[id]['access_key_id'], d[id]['secret_access_key'])
  print(str(len(accounts)) + ' aws profiles configured')
  
# Start the show
if __name__ == '__main__':
    main()



#/usr/bin/env python3

import os
import json
import webpy
import sys
import argparse
import datetime
import requests
import shutil

if sys.version_info < (3,0,0):
    print("ERROR: Please run with Python 3!")
    sys.exit()

IDFILE = "myid.txt"
mydir = os.path.dirname(os.path.abspath(__file__))

SERVER_HOSTNAME = "128.30.195.11"
SERVER_PORT = 39284

MY_VERSION = (1,0,2)

client = webpy.WebPyClient(SERVER_HOSTNAME, SERVER_PORT, codec=webpy.WebPyJSONCodec)

def check_for_updates():
    response = requests.get('http://6.869.csail.mit.edu/fa19/miniplaces_part2/client_version.txt')
    if response.status_code == 200:
        curr_ver = tuple(map(int, response.text.split('.')))
    if curr_ver > MY_VERSION:
        print("Sorry! Not using the newest Miniplaces Client version.")
        if input("May I update? (Y/N)").lower().startswith('y'):
            print("Updating...")
            response_updated = requests.get('http://6.869.csail.mit.edu/fa19/miniplaces_part2/client.py')
            if response_updated.status_code == 200:
                with open(os.path.join(mydir, "updated_client.py"), "wb") as f:
                    f.write(response_updated.content)
                print("Swapping...")
                shutil.copy2(os.path.join(mydir, "updated_client.py"), __file__)
                try:
                    os.remove(os.path.join(mydir, "updated_client.py"))
                except:
                    print("Couldn't remove updated_client.py. Please remove manually.")
                print("Swap successful! (I think). Exiting... Rerun for latest updates")
                sys.exit(0)
            else:
                print("Failed to fetch updates! Try going to:\n%s\nto manually replace this file" % "http://6.869.csail.mit.edu/fa19/miniplaces_part2/client.py")
                sys.exit(1)
    else:
        print("Newest version!")
            

def request_generate_teamid(team_name, kerb1, kerb2):
    gen_id = client.generate_id(team_name, kerb1, kerb2)['team_id']
    with open(os.path.join(mydir, IDFILE), 'w') as f:
        f.write(gen_id)
        f.write("\n")
    print("Team ID generated and written to %s" % IDFILE)

def read_id():
    with open(os.path.join(mydir, IDFILE), 'r') as f:
        team_id = f.read()
    print("Using Team ID: %s" % team_id)
    return team_id

def get_teamid():
    if not os.path.exists(os.path.join(mydir, IDFILE)):
        # The id file does not exist yet
        print("Could not find myid.txt - Requesting a new team submission code.")
        team_name = input("Enter your chosen team name, which will appear on the leaderboards: ")
        kerb1 = input("Enter the kerberos of the first person: ")
        kerb2 = input("Enter the kerberos of the second person (leave blank if 1 person team): ")
        request_generate_teamid(team_name, kerb1, kerb2)
    team_id = read_id()
    return team_id

def show_leaderboard():
    response = client.get_leaderboard()
    for rank, (team_name, score) in enumerate(response['scores'], 1):
        print("%2d. (%06.4f) %s" % (rank, float(score), team_name))

def submit_file(fp):
    with open(fp, 'r') as f:
        predictions = json.load(f)
    response = client.submit(get_teamid(), predictions)
    sid = response['submission_id']
    print("Submitted %s. Submission ID: %s" % (os.path.basename(fp), sid))

def show_my_scores():
    response = client.get_my_scores(get_teamid())
    print("My submissions:")
    for (timestamp, team_name, score) in response['scores']:
        print("%s | %s" % (timestamp, score))
    
def show_aws_credits():
    response = client.get_aws_credit(get_teamid())
    print("My AWS credit (email if you need more - we do not expect this, though):")
    print(response['credits'])


def parse_args():
    parser = argparse.ArgumentParser("Submits / Views Submissions to the 6.869 Miniplaces Challenge Server")
    parser.add_argument("mode", choices=["leaderboard","submit","view", "aws"], help="What operation to do. View the leaderboard (leaderboard), submit predictions (submit), get AWS credits (aws) or view your previous scores (view)")
    parser.add_argument("submission", type=os.path.abspath, nargs='?', default=None, help="The .json file to submit")
    args = parser.parse_args()
    if 'mode' == 'submit':
        if args.submission is None:
            print("You must provide the <submission> argument if submitting a file. Use -h for more info")
            sys.exit(1)
        if not os.path.isfile(args.submission):
            print("Could not find the file:\n%s" % args.submission)
            sys.exit(1)
    return args


def main():
    check_for_updates()
    args = parse_args()
    if args.mode == 'leaderboard':
        show_leaderboard()
    elif args.mode == 'submit':
        submit_file(args.submission)
        # Show the scores if you just submitted
        show_my_scores()
    elif args.mode == 'aws':
        show_aws_credits()
    if args.mode == 'view':
        show_my_scores()

if __name__ == "__main__":
    main()

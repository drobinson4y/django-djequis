"""SKY API Authentication/Query Scripts
Modified from code by Mitch Hollberg
(mhollberg@gmail.com, mhollberg@cfgreateratlanta.org)
Python functions to
    a) Get an initial SKYApi token/refresh token and write them to a local file
    b) Make subsequent refreshes and updates to the SKYApi authentication
    based on tokens in the files.
"""

# from pathlib import Path
import os
import sys
import requests
import json
import time
import base64
import datetime as dt
from datetime import datetime
import django
import os.path
import csv

# Note to self, keep this here
# django settings for shell environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "djequis.settings")
import django
django.setup()

# django settings for script
from django.conf import settings

# informix environment
os.environ['INFORMIXSERVER'] = settings.INFORMIXSERVER
os.environ['DBSERVERNAME'] = settings.DBSERVERNAME
os.environ['INFORMIXDIR'] = settings.INFORMIXDIR
os.environ['ODBCINI'] = settings.ODBCINI
os.environ['ONCONFIG'] = settings.ONCONFIG
os.environ['INFORMIXSQLHOSTS'] = settings.INFORMIXSQLHOSTS
# ________________
from django.conf import settings
from django.core.cache import cache
from sky_api_auth import token_refresh
from sky_api_calls import api_get, get_const_custom_fields, \
    get_constituent_id, set_const_custom_field, update_const_custom_fields, \
    delete_const_custom_fields, get_relationships, api_post, api_patch, \
    api_delete, get_custom_fields, get_custom_field_value, get_constituent_list
from djzbar.utils.informix import get_engine
from djzbar.utils.informix import do_sql
from djzbar.settings import INFORMIX_EARL_SANDBOX
from djzbar.settings import INFORMIX_EARL_TEST
from djzbar.settings import INFORMIX_EARL_PROD
from djtools.fields import TODAY

# normally set as 'debug" in SETTINGS
DEBUG = settings.INFORMIX_DEBUG

"""
    The process would have to involve finding the status of active students
    in CX, (Look for a change date...to limit the number.  Maybe audit table)
    Then determine if the student is in Raiser's Edge
    If not add student, then add the custom field record
    Else - find out of custom field record exists
        If not add
        else update
    So each student will require 2-3 API calls
    --
    No way to test any of this because there are no students in RE yet...
"""

def main():
    try:

        # set global variable
        global EARL
        # determines which database is being called from the command line
        # if database == 'cars':
        EARL = INFORMIX_EARL_PROD
        # if database == 'train':
        #     EARL = INFORMIX_EARL_TEST
        # elif database == 'sandbox':
        #     EARL = INFORMIX_EARL_SANDBOX
        # else:
            # this will raise an error when we call get_engine()
            # below but the argument parser should have taken
            # care of this scenario and we will never arrive here.
            # EARL = None
        # establish database connection
        engine = get_engine(EARL)


        # for now, possible actions include get_id = which will bypass
        # all the others, set_status, update_status, delete_field,
        # get_relationships

        action = ''
        # action = 'set_status'
        # action = 'update_status'
        # action = 'delete_field'
        # action = 'get_relationships'

        """--------REFRESH THE TOKEN------------------"""
        """ Because the token only lasts for 60 minutes when things are idle
            it will be necessary to refresh the token before attempting
            anything else.   The refresh token will be valid for 60 days,
            so it should return a new token with no problem.  All the API
            calls will get new tokens, resetting the 60 minute clock, 
            so to avoid calling for a token every time, I may have to 
            either set a timer or see if I can read the date and time from the
            cache files and compare to current time
         """

        """Check to see if the token has expired, if so refresh it
            the token expires in 60 minutes, but the refresh token
            is good for 60 days"""
        t = cache.get('refreshtime')

        if t < datetime.now() - dt.timedelta(minutes=59):
            print('Out of token refresh limit')
            print(t)
            print(datetime.now() - dt.timedelta(minutes=59))
            r = token_refresh()
            print(r)
        else:
            print("within token refresh limit")


        """"--------GET THE TOKEN------------------"""
        current_token = cache.get('tokenkey')
        # print("Current Token = ")
        # print(current_token)

        """ --------GET THE BLACKBAUD CONSTITUENT ID-----------------"""
        """ I will either have a list of students in a csv file or possibly
            in  a to be determined database
            That way I can get the blackbaud internal id en masse and
            not need to make multiple calls based on the carthage ID
            I may also look to see if the student status has changed in 
            CX

            select * from cars_audit:prog_enr_rec
            where acst =  'WD'
            and audit_timestamp > TODAY - 1
            
            select * from cars_audit:stu_acad_rec
            where acst =  'WD'
            and yr = 2019 and sess = 'RA'
            and audit_timestamp > TODAY - 100
        
        """
        statquery= '''select distinct id, acst 
            from cars_audit:prog_enr_rec 
            where acst =  'WD'
            and audit_event = 'AU'
            and audit_timestamp > TODAY - 1'''

        ret = do_sql(statquery, key=DEBUG, earl=EARL)
        for i in ret:
            print(i)


        with open("id_list.csv", 'r') as id_lst:
            reed = csv.reader(id_lst, delimiter=',')
            for row in reed:
                # print(row)
                const_id = row[1]

        # # # First, we have to get the internal ID from blackbaud for
        # # the constituent
        # const_id = get_constituent_id(current_token, 1534657)
        print("Constituent id = " + str(const_id))




        """------GET CUSTOM FIELDS FOR A CONSTITUENT----------"""
        # Also need to check to see if the custom field exists
        # Does not appear we can filter by category or type...WHY???
        # NEED TO GRAB THE ITEM ID FROM THE SPECIFIC CUSTOM FIELD
        # NOTE:  There seems to be a delay between successfully creating a
        # custom field value and being able to retrieve it for the student
        category = 'Student Status'
        ret = get_const_custom_fields(current_token, const_id, category)
        # print(ret)
        item_id = ret
        # print("Item ID = " + str(item_id))

        """
        --------------------------
        Here we will need some logic.   
        API options are POST, PATCH, DELETE   
        If the constituent exists and has the specific custom field 
        Student Status, then we need to update
        the existing record, if not we need to add it
        ---------------------------
        """

        if action == 'set_status':
            """-----POST-------"""
            # Then we can deal with the custom fields...
            comment = 'Testing an add'
            val = 'Administrator'
            category = 'Student Status'
            ret = set_const_custom_field(current_token, const_id, val,
                                         category, comment)
            print(ret)

        if action == 'update_status':
            """-----PATCH-------"""
            # Required:  Token, Item ID
            # Need to test to see if all remaining params must be passed or if
            # we only pass the ones that change...We shouldn't need to change the
            # category or type...Would think date added should also
            # remain unchanged
            # category = 'Involvement'
            comment = 'Test 110319'
            valu = 'Not a Student'
            ret = update_const_custom_fields(current_token, item_id, comment, valu)
            print(ret)

            """-----DELETE-------"""
        if action == 'delete_field':
            ret = delete_const_custom_fields(current_token, item_id)
            print(ret)

        '''
        -----------------------------------
        A different routine from the custom fields.
        -----------------------------------
        '''
        if action == 'get_relationships':
            """-----RELATIONSHIPS FOR A CONSTITUENT-------"""
            ret = get_relationships(current_token, const_id)
            print(ret)

        # """ --------These are generic and not specific to a constituent---"""
        # ret = get_custom_fields(current_token)
        # ret = get_custom_field_value(current_token, 'Involvment')

        # """-----Once done, the token must be refreshed-------"""
        # Changed this.   Test at top to see if token has expired, then
        # Refresh the API tokens
        # r = token_refresh()
        # print(r)

    except Exception as e:
        print("Error in main:  " + e.message)
        # fn_write_error("Error in misc_fees.py - Main: "
        #                + e.message)


if __name__ == "__main__":
    # args = parser.parse_args()
    # test = args.test
    # database = args.database

    # if not database:
    #     print "mandatory option missing: database name\n"
    #     parser.print_help()
    #     exit(-1)
    # else:
    #     database = database.lower()

    # if database != 'cars' and database != 'train' and database != 'sandbox':
    #     print "database must be: 'cars' or 'train' or 'sandbox'\n"
    #     parser.print_help()
    #     exit(-1)
    #
    # if not test:
    #     test = 'prod'
    # else:
    #     test = "test"

    sys.exit(main())

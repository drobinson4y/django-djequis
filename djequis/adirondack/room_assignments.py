import hashlib
import json
import os
import sys
import time
import datetime
from datetime import datetime
import requests
import csv
import argparse
import django
# ________________
# Note to self, keep this here
# django settings for shell environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "djequis.settings")
django.setup()
# ________________

from django.conf import settings
from djequis.core.utils import sendmail
from djzbar.utils.informix import do_sql
from djzbar.utils.informix import get_engine
from djtools.fields import TODAY
from djzbar.settings import INFORMIX_EARL_SANDBOX
from djzbar.settings import INFORMIX_EARL_TEST
from djzbar.settings import INFORMIX_EARL_PROD
from adirondack_sql import ADIRONDACK_QUERY, Q_GET_TERM
from utilities import fn_write_error, fn_write_billing_header, \
    fn_write_assignment_header, fn_get_utcts, fn_encode_rows_to_utf8, \
    fn_get_bill_code, fn_fix_bldg, fn_mark_room_posted, \
    fn_translate_bldg_for_adirondack

# informix environment
os.environ['INFORMIXSERVER'] = settings.INFORMIXSERVER
os.environ['DBSERVERNAME'] = settings.DBSERVERNAME
os.environ['INFORMIXDIR'] = settings.INFORMIXDIR
os.environ['ODBCINI'] = settings.ODBCINI
os.environ['ONCONFIG'] = settings.ONCONFIG
os.environ['INFORMIXSQLHOSTS'] = settings.INFORMIXSQLHOSTS
os.environ['LD_LIBRARY_PATH'] = settings.LD_LIBRARY_PATH
os.environ['LD_RUN_PATH'] = settings.LD_RUN_PATH

# normally set as 'debug" in SETTINGS
DEBUG = settings.INFORMIX_DEBUG

# set up command-line options
desc = """
    Collect adirondack data Room assignments for stu_serv_rec
"""
parser = argparse.ArgumentParser(description=desc)

parser.add_argument(
    "--test",
    action='store_true',
    help="Dry run?",
    dest="test"
)
parser.add_argument(
    "-d", "--database",
    help="database name.",
    dest="database"
)
parser.add_argument(
    "-run_mode",
    help="Manual or scheduled run?",
    dest="run_mode"
)


def main():
    try:
        #    Term will be RA+Current year
        #  One big push for returning students May 1 for RC term
        #    Only returning will be in the system, no need to screen out frosh
        #  Push again June 30 and July 30  for RC term (will include frosh)
        #  Aug 1 start automation for fall term
        #  For spring RC+Nextyear push...third Wednesday in December
        #  Stop automation for RC on last day of class - appr May 20
        #  Automation could just take the current term
        #  May 1, June 30, July 30 December  for upcoming term

        # From Aug to Dec, grab all RA current year
        # From Jan to May 1 grab all RC current year
        # On MAY 1, grab all RA current year
        # on June 30 grab all RA current year
        # On third wednesday in December grab all RC Next
        # On Next day in Dec, go back to RA Current
        
        # Only options are RC20xx and RA20xx, so I only need to determine
        # which year to pass during each time frame.
        # Question is, for spring housing, will both RA and RC need to be
        # dealt with?

        # set global variable
        global EARL
        # determines which database is being called from the command line
        # if database == 'cars':
        # EARL = INFORMIX_EARL_PROD
        if database == 'train':
            EARL = INFORMIX_EARL_TEST
        elif database == 'sandbox':
            EARL = INFORMIX_EARL_SANDBOX
        else:
            # # this will raise an error when we call get_engine()
            # below but the argument parser should have taken
            # care of this scenario and we will never arrive here.
            EARL = None
            # establish database connection


        engine = get_engine(EARL)

        # try:

        utcts = fn_get_utcts()
        # print("Seconds from UTC Zero hour = " + str(utcts))
        hashstring = str(utcts) + settings.ADIRONDACK_API_SECRET
        # print("Hashstring = " + hashstring)

        # Assumes the default UTF-8
        hash_object = hashlib.md5(hashstring.encode())
        # print(hash_object.hexdigest())
        # print("Time of send = " + time.strftime("%Y%m%d%H%M%S"))
        datetimestr = time.strftime("%Y%m%d%H%M%S")

        if run_mode == "manual":
            print("Manual Mode")
            session = raw_input("Enter target session (EX. RA 2019):  ")
            hall = fn_translate_bldg_for_adirondack(
                raw_input("Enter Hall code: "))

        elif run_mode == "auto":

            # Get the current term
            ret = do_sql(Q_GET_TERM, key=DEBUG, earl=EARL)
            if ret is not None:
                row = ret.fetchone()
                if row is None:
                    print("Term not found")
                else:
                    session = row[0]
                    hall = ''
                # IMPORTANT! won't work if string has any spaces.  NO SPACES


        print("Session = " + session)
        print("hall = " + hall)

        url = "https://carthage.datacenter.adirondacksolutions.com/" \
            "carthage_thd_test_support/apis/thd_api.cfc?" \
            "method=housingASSIGNMENTS&" \
            "Key=" + settings.ADIRONDACK_API_SECRET + "&" \
            "utcts=" + \
            str(utcts) + "&" \
            "h=" + hash_object.hexdigest() + "&" \
            "TimeFrameNumericCode=" + session + "&" \
            "Posted=0" + "&" \
            "HALLCODE=" + hall

        print(url)

        # NOTE:  HALLCODE can be empty
        # "STUDENTNUMBER=" + "1560943"
        # "CurrentFuture=-1" + "&" \
        #                      "Ghost=0" + "&" \

            # DO NOT MARK AS POSTED HERE - DO IT IN SECOND STEP
        # "PostAssignments=-1" + "&" \

        # + "&" \
        # "HallCode=" + 'SWE'

        # DEFINITIONS
        # Posted: 0 returns only NEW unposted,
        # 1 returns posted, as in out to our system
        # 2 changed or cancelled
        # PostAssignments: -1 will mark the record as posted.
        # CurrentFuture: -1 returns only current and future
        # Cancelled: -1 is for cancelled, 0 for not cancelled

        # print("URL = " + url)

        # In theory, every room assignment in Adirondack should have
        # a bill code

        response = requests.get(url)
        x = json.loads(response.content)
        # print(x)
        if not x['DATA']:
            print("No new data found")
        else:
            room_file = settings.ADIRONDACK_TXT_OUTPUT + \
                        settings.ADIRONDACK_ROOM_ASSIGNMENTS + '.csv'
            # print(room_file)
            room_archive = settings.ADIRONDACK_ROOM_ARCHIVED + \
                settings.ADIRONDACK_ROOM_ASSIGNMENTS + \
                datetimestr + '.csv'
            # print(room_archive)

            if os.path.exists(room_file):
                os.rename(room_file, room_archive)

            # IF directly updating stu_serv_rec, writing csv may be
            # redundant
            # fn_write_assignment_header()
            room_data = fn_encode_rows_to_utf8(x['DATA'])
            # print("Start Loop")

            with open(room_file, 'ab') as room_output:
                for i in room_data:
                    print("______")
                    print(i[0])
                    carthid = i[0]
                    bldgname = i[1]
                    adir_hallcode = i[2]
                    bldg = fn_fix_bldg(i[2])
                    print("Adirondack Hall Code = " + adir_hallcode)
                    floor = i[3]
                    bed = i[5]
                    room_type = i[6]
                    occupancy = i[7]
                    roomusage = i[8]
                    timeframenumericcode = i[9]
                    checkin = i[10]
                    if i[11] == None:
                        checkedindate = None
                    else:
                        d1 = datetime.strptime(i[11],
                                               "%B, "
                                               "%d %Y "
                                               "%H:%M:%S")
                        checkedindate = d1.strftime("%m-%d-%Y")
                    # print("ADD DATE = " + str(checkedindate))
                    checkout = i[12]
                    if i[13] == None:
                        checkedoutdate = None
                    else:
                        d1 = datetime.strptime(i[13],
                                               "%B, "
                                               "%d %Y "
                                               "%H:%M:%S")
                        checkedoutdate = d1.strftime("%m-%d-%Y")
                    # print("OUT DATE = " + str(checkedoutdate))
                    po_box = i[14]
                    po_box_combo = i[15]
                    canceled = i[16]
                    canceldate = i[17]
                    cancelnote = i[18]
                    cancelreason = i[19]
                    ghost = i[20]
                    posted = i[21]
                    roomassignmentid = i[22]
                    sess = i[9][:2]
                    year = i[9][-4:]
                    term = i[9]
                    occupants = i[7]
                    billcode = fn_get_bill_code(carthid, str(bldg),
                                                room_type,
                                                roomassignmentid,
                                                session)
                    # print("Bill Code =  " + billcode)
                    # Intenhsg can b R = Resident, O = Off-Campus,
                    # C = Commuter
                    # print(bldgname)
                    # print(bldgname.find('_'))
                    # print(bldgname[(bldgname.find('_') + 1)
                    #       - len(bldgname):])
                    # print(len(bldgname))

                    # This if routine is needed because the adirondack
                    # hall codes match to multiple descriptions and
                    # hall descriptions have added qualifiers such as
                    # FOFF, MOFF, UNF, LOCA that are not available
                    # elsewhere using the API.  Have to parse it to
                    # assign a generic room
                    # For non residents, we have a generic room for
                    # CX and a dummy room on the Adirondack side
                    # So we need two variables, on for Adirondack and
                    # one for CX.

                    adir_room = i[4]

                    if bldg == 'CMTR':
                        intendhsg = 'C'
                        room = bldgname[(bldgname.find('_') + 1)
                                        - len(bldgname):]
                    elif bldg == 'OFF':
                        intendhsg = 'O'
                        room = bldgname[(bldgname.find('_') + 1)
                                        - len(bldgname):]
                    elif bldg == 'ABRD':
                        intendhsg = 'O'
                        room = bldgname[(bldgname.find('_') + 1)
                                        - len(bldgname):]
                    elif bldg == 'UN':
                        intendhsg = 'O'
                        room = bldgname[(bldgname.find('_') + 1)
                                        - len(bldgname):]
                    else:
                        intendhsg = 'R'
                        room = i[4]

                    # Use cancelation reason
                    if cancelreason == 'Withdrawal':
                        rsvstat = 'W'
                        billcode = 'NOCH'
                    else:
                        rsvstat = 'R'

                    # This may be useful to determine which records
                    # have been pulled and processed
                    print("ROOMASSIGNMENTID = "
                          + str(roomassignmentid))

                    csvWriter = csv.writer(room_output,
                                           quoting=csv.QUOTE_NONNUMERIC
                                           )
                    # csvWriter.writerow(i)
                    # Need to write translated fields if csv is to
                    # be created
                    csvWriter.writerow([carthid, bldgname, bldg,
                                        floor, room, bed, room_type,
                                        occupancy, roomusage,
                                        timeframenumericcode, checkin,
                                        checkedindate, checkout,
                                        checkedoutdate, po_box,
                                        po_box_combo, canceled,
                                        canceldate, cancelnote,
                                        cancelreason, ghost, posted,
                                        roomassignmentid])
                    # print(str(carthid) + ', ' + str(billcode) + ', '
                    #       + str(bldg) + ', ' + str(room) + ', ' +
                    #       + str(room_type))
                    # Validate if the stu_serv_rec exists first
                    # update stu_serv_rec id, sess, yr, rxv_stat,
                    # intend_hsg, campus, bldg, room, bill_code
                    q_validate_stuserv_rec = '''
                                  select id, sess, yr, rsv_stat, 
                                  intend_hsg, campus, bldg, room, 
                                  no_per_room, 
                                  add_date, 
                                  bill_code, hous_wd_date 
                                  from stu_serv_rec 
                                  where yr = {2}
                                  and sess  = "{1}"
                                  and id = {0}'''.format(carthid,
                                                         sess, year)
                    # print(q_validate_stuserv_rec)

                    ret = do_sql(q_validate_stuserv_rec, key=DEBUG,
                                 earl=EARL)

                    if ret is not None:
                        if billcode > 0:
                            # compare rsv_stat, intend_hsg, bldg, room,
                            # billcode
                            # Update only if something has changed
                            print("Record found " + carthid)

                            row = ret.fetchone()
                            if row is not None:
                                print(row[3] + "," + str(rsvstat))
                                print(row[4] + "," + str(intendhsg))
                                print(row[6] + "," + str(bldg))
                                print(row[7] + "," + str(room))
                                print(row[10] + "," + str(billcode))
                                if row[3] != rsvstat \
                                        or row[4] != intendhsg \
                                        or row[6] != bldg \
                                        or row[7] != room \
                                        or row[10] != billcode:
                                    print("Need to update "
                                          "stu_serv_rec")
                                    q_update_stuserv_rec = '''
                                    UPDATE stu_serv_rec set  
                                    rsv_stat = ?,
                                    intend_hsg = ?, campus = ?, 
                                    bldg = 
                                    ?, room = ?,
                                    no_per_room = ?, add_date = ?, 
                                    bill_code = ?,
                                    hous_wd_date = ?
                                    where id = ? and sess = ? and 
                                    yr = ?'''
                                    q_update_stuserv_args = (rsvstat,
                                        intendhsg,
                                        "MAIN", bldg,
                                        room,
                                        occupants,
                                        checkedindate,
                                        billcode,
                                        checkedoutdate,
                                        carthid,
                                        sess, year)
                                    # print(q_update_stuserv_rec)
                                    # print(q_update_stuserv_args)
                                    engine.execute(
                                        q_update_stuserv_rec,
                                        q_update_stuserv_args)

                                    fn_mark_room_posted(carthid,
                                                   adir_room,
                                                   adir_hallcode, term)

                                else:
                                    print("No change needed in "
                                          "stu_serv_rec")
                                    fn_mark_room_posted(carthid,
                                                   adir_room,
                                                   adir_hallcode, term)

                            else:
                                print("fetch retuned none - No "
                                      "stu_serv_rec for student "
                                      + carthid + " for term " + term)

                        else:
                            print("Bill code not found")
                    #     # go ahead and update
                    else:
                        print("Record not found")

                        body = "Student Service Record does not " \
                               "exist. Please inquire why."
                        subj = "Adirondack - Stu_serv_rec missing"
                        sendmail("dsullivan@carthage.edu",
                                 "dsullivan@carthage.edu", body, subj)

                        # Insert if no record exists, update else
                        # Dave says stu_serv_rec should NOT be created
                        # from Adirondack data.  Other offices need
                        # to create the initial record
                        # Need to send something to Marietta
                        # if billcode > 0:
                        #     q_insert_stuserv_rec = '''
                        #             INSERT INTO stu_serv_rec (id,
                        #             sess, yr, rsv_stat, intend_hsg,
                        #             campus, bldg, room, no_per_room,
                        #             add_date,bill_code, hous_wd_date)
                        #             VALUES (?,?,?,?,?,?,?,?,?,?,?)'''
                        #     q_insert_stuserv_args = (
                        #         carthid, term, yr, rsvstat, 'R',
                        #         'MAIN', bldg, room, occupants,
                        #         checkedindate, billcode,
                        #         checkedoutdate)
                        #     print(q_insert_stuserv_rec)
                        #     print(q_insert_stuserv_args)
                        #     # engine.execute(q_insert_stuserv_rec,
                        #     # q_insert_stuserv_args)

                        # else:
                        #     print("Bill code not found")

        # filepath = settings.ADIRONDACK_CSV_OUTPUT

    except Exception as e:
        print(
                "Error in adirondack_room_assignments_api.py- Main:  " +
                e.message)
        # fn_write_error("Error in adirondack_std_billing_api.py - Main: "
        #                + e.message)


if __name__ == "__main__":
    args = parser.parse_args()
    test = args.test
    database = args.database
    run_mode = args.run_mode

    if not database:
        print "mandatory option missing: database name\n"
        parser.print_help()
        exit(-1)
    else:
        database = database.lower()

    if database != 'cars' and database != 'train' and database != 'sandbox':
        print "database must be: 'cars' or 'train' or 'sandbox'\n"
        parser.print_help()
        exit(-1)

    if not run_mode:
        print "mandatory option missing: run_mode\n"
        parser.print_help()
        exit(-1)
    else:
        database = database.lower()

    if run_mode != 'manual' and run_mode != 'auto':
        print "run_mode must be: 'manual' or 'auto'"
        parser.print_help()
        exit(-1)

    sys.exit(main())


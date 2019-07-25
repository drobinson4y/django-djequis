import hashlib
import json
import os
import requests
import csv
# prime django
import django
# django settings for script
from django.conf import settings
from django.db import connections
from djequis.core.utils import sendmail
from djzbar.utils.informix import do_sql
from djzbar.utils.informix import get_engine
from djtools.fields import TODAY
from djzbar.settings import INFORMIX_EARL_TEST
from djzbar.settings import INFORMIX_EARL_PROD
from adirondack_sql import ADIRONDACK_QUERY
from adirondack_utilities import fn_write_error, fn_write_billing_header, \
    fn_write_assignment_header, fn_get_utcts

# django settings for shell environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "djequis.settings")


django.setup()

#
os.environ['INFORMIXSERVER'] = settings.INFORMIXSERVER
# informix environment
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
    Collect adirondack data ASCII Post
"""


def encode_rows_to_utf8(rows):
    encoded_rows = []
    for row in rows:
        try:
            encoded_row = []
            for value in row:
                if isinstance(value, basestring):
                    value = value.decode('cp1252').encode("utf-8")
                encoded_row.append(value)
            encoded_rows.append(encoded_row)
        except Exception as e:
            fn_write_error("Error in encoded_rows routine " + e.message)
    return encoded_rows


def get_bill_code(idnum, bldg):
    utcts = fn_get_utcts()

    hashstring = str(utcts) + settings.ADIRONDACK_API_SECRET

    hash_object = hashlib.md5(hashstring.encode())
    url = "https://carthage.datacenter.adirondacksolutions.com/" \
          "carthage_thd_test_support/apis/thd_api.cfc?" \
          "method=studentBILLING&" \
          "Key=" + settings.ADIRONDACK_API_SECRET + "&" + "utcts=" + \
          str(utcts) + "&" + "h=" + \
          hash_object.hexdigest() + "&" + \
          "ItemType=Housing&" + \
          "STUDENTNUMBER=" + idnum + "&" + \
          "TIMEFRAMENUMERICCODE=RA 2019"

    response = requests.get(url)
    x = json.loads(response.content)
    # print(x)
    if not x['DATA']:
        print("No data")
        if bldg == 'CMTR':
            billcode = 'CMTR'
        elif bldg == 'OFF':
            billcode = 'OFF'
        elif bldg == 'ABRD':
            billcode = 'ABRD'
        else:
            billcode = ''
        return billcode
    else:
        for i in x['DATA']:
            print(i[6])
            billcode = i[6]
            return billcode


def main():
    try:
        # set global variable
        global EARL
        # determines which database is being called from the command line
        # if database == 'cars':
        #     EARL = INFORMIX_EARL_PROD
        # if database == 'train':
        EARL = INFORMIX_EARL_TEST
        # elif database == 'sandbox':
        #     EARL = INFORMIX_EARL_SANDBOX
        # else:
        # this will raise an error when we call get_engine()
        # below but the argument parser should have taken
        # care of this scenario and we will never arrive here.
        # EARL = None
        # establish database connection
        # engine = get_engine(EARL)

    # try:
        utcts = fn_get_utcts()
        # print("Seconds from UTC Zero hour = " + str(utcts))
        hashstring = str(utcts) + settings.ADIRONDACK_API_SECRET
        # print("Hashstring = " + hashstring)

        # Assumes the default UTF-8
        hash_object = hashlib.md5(hashstring.encode())
        # print(hash_object.hexdigest())
        # print("Time of send = " + time.strftime("%Y%m%d%H%M%S"))

        q_get_term = '''select trim(trim(sess)||' '||trim(TO_CHAR(yr))) session
                        from acad_cal_rec
                        where sess in ('RA','RC')
                        and subsess = ''
                        and first_reg_date < TODAY
                        and charge_date > TODAY
                         '''
        ret = do_sql(q_get_term, key=DEBUG, earl=EARL)
        if ret is not None:
            row = ret.fetchone()
            if row is not None:
                session = row[0]
                print("Session = " + session)

            url = "https://carthage.datacenter.adirondacksolutions.com/" \
                  "carthage_thd_test_support/apis/thd_api.cfc?" \
                  "method=housingASSIGNMENTS&" \
                  "Key=" + settings.ADIRONDACK_API_SECRET + "&" \
                  "utcts=" + str(utcts) + "&" \
                  "h=" + hash_object.hexdigest() + "&" \
                  "TimeFrameNumericCode=" + session + "&" \
                  "STUDENTNUMBER=" + "1535266"
                  # "STUDENTNUMBER=" + "1539775,1475918,1435328,1501195,1561509,1496108,1408374,1478479"
                  # "HallCode=" + 'SWE'
                  # + "&" \
                  # "CurrentFuture=-1"
                  # + "&"
                  # "HallCode=DEN,JOH,OAKS1,OAKS2,OAKS3,OAKS4,OAKS5,OAKS6,MADR,SWE," \
                  #     "TAR,TOWR,UN,OFF,ABRD,CMTR,''"

                  # print("URL = " + url)
        else:
            print("Term not found")


        # NOTE # # NOTE # # NOTE # # NOTE # # NOTE # # NOTE # # NOTE #
        # I could flip this, grab only the records of a bill for room and
        #   board, and use that record to go and get the room assignment
        # NOTE # # NOTE # # NOTE # # NOTE # # NOTE # # NOTE # # NOTE #

        response = requests.get(url)
        x = json.loads(response.content)
        # print(x)
        if not x['DATA']:
            print("No match")
        else:
            # IF directly updating stu_serv_rec, writing csv may be redundant
            fn_write_assignment_header()
            z = encode_rows_to_utf8(x['DATA'])
            # print("Start Loop")
            with open(settings.ADIRONDACK_ROOM_ASSIGNMENTS,
                      'ab') as room_output:
                for i in z:
                    carthid = i[0]
                    bldgname = i[1]
                    bldg = i[2]
                    floor = i[3]
                    bed = i[5]
                    room_type = i[6]
                    occupancy = i[7]
                    roomusage = i[8]
                    timeframenumericcode = i[9]
                    checkin = i[10]
                    checkedindate = i[11]
                    checkout = i[12]
                    checkedoutdate = i[13]
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

                    billcode = get_bill_code(carthid, str(bldg))
                    # Intenhsg can b R = Resident, O = Off-Campus, C = Commuter
                    if bldg == 'CMTR':
                        intendhsg = 'C'
                        room = 'CMTR'
                    elif bldg == 'OFF':
                        intendhsg = 'O'
                        room = 'OFF'
                    elif bldg == 'ABRD':
                        intendhsg = 'O'
                        room = 'ABRD'
                    else:
                        intendhsg = 'R'
                        room = i[4]

                    # Use cancelation reason
                    if cancelreason == 'Withdrawal':
                        rsvstat = 'W'
                    else:
                        rsvstat = 'R'


                    csvWriter = csv.writer(room_output,
                                           quoting=csv.QUOTE_NONE)
                    # csvWriter.writerow(i)
                    # Need to write translated fields if csv is to be created
                    csvWriter.writerow([carthid, bldgname, bldg, floor, room,
                                bed, room_type, occupancy, roomusage,
                                timeframenumericcode, checkin, checkedindate,
                                checkout, checkedoutdate, po_box, po_box_combo,
                                canceled, canceldate, cancelnote, cancelreason,
                                ghost, posted, roomassignmentid])
                    print(str(carthid) + ', ' + str(billcode) + ', ' + str(bldg) + str(room)
                          + str(room_type))
                    # Validate if the stu_serv_rec exists first
                    # update stu_serv_rec id, sess, yr, rxv_stat, intend_hsg,
                    # campus, bldg, room, bill_code
                    q_validate_stuserv_rec = '''
                                  select id, sess, yr, rsv_stat, 
                                  intend_hsg, campus, bldg, room, no_per_room, 
                                  add_date, 
                                  bill_code, hous_wd_date 
                                  from stu_serv_rec 
                                  where yr = {2}
                                  and sess  = "{1}"
                                  and id = {0}'''.format(carthid, sess, year)
                    # print(q_validate_stuserv_rec)

                    ret = do_sql(q_validate_stuserv_rec, key=DEBUG, earl=EARL)

                    if ret is not None:
                        if billcode > 0:
                            # compare rsv_stat, intend_hsg, bldg, room, billcode
                            # Update only if something has changed
                            print("Record found " + carthid)

                            row = ret.fetchone()
                            if row is not None:
                                RSVSTAT = row[3]
                                INTHSG = row[4]
                                BLDG = row[6]
                                ROOM = row[7]
                                BILLCODE = row[10]
                                print("Current Stu Serv Data = " + RSVSTAT,INTHSG,BLDG,ROOM,BILLCODE)
                                # print("Session = " + session)

                                if row[3] != rsvstat or row[4] != intendhsg \
                                        or row[6] != bldg or row[7] != room \
                                        or row[10] != billcode:
                                    print("Need to update stu_serv_rec")
                                else:
                                    print("No change needed in stu_serv_rec")

                            q_update_stuserv_rec = '''
                                UPDATE stu_serv_rec set  rsv_stat = ?,
                                intend_hsg = ?, campus = ?, bldg = 
                                ?, room = ?,
                                no_per_room = ?, add_date = ?, 
                                bill_code = ?,
                                hous_wd_date = ?)
                                where id = ? and sess = ? and yr = ?'''
                            q_update_stuserv_args = (rsvstat, intendhsg,
                                    "Main", bldg,
                                    room, occupants, checkedindate, billcode,
                                    checkedoutdate, carthid, sess, year)
                            # print(q_update_stuserv_rec)
                            print(q_update_stuserv_args)
                        else:
                            print("Bill code not found")
                    #     # go ahead and update
                    else:
                        print("Record not found")
                        # Insert if no record exists, update else
                        if billcode > 0:
                            q_insert_stuserv_rec = '''
                                    INSERT INTO stu_serv_rec (id, sess, yr, 
                                    rsv_stat, intend_hsg, campus, bldg, room, 
                                    no_per_room,
                                    add_date,
                                    bill_code, hous_wd_date)
                                    VALUES (?,?,?,?,?,?,?,?,?,?,?)'''
                            q_insert_stuserv_args = (
                                    carthid, term, yr, rsvstat, 'R', 'MAIN',
                                    bldg, room, occupants,
                                    checkedindate, billcode, checkedoutdate)
                            print(q_insert_stuserv_rec)
                            print(q_insert_stuserv_args)
                            # engine.execute(q_insert_stuserv_rec,
                            # q_insert_stuserv_args)
            
                        else:
                            print("Bill code not found")

                # NOTE ABOUT WITHDRAWALS!!!!
                # Per Amber, the only things that get changed when a student
                # withdraws
                # are setting the rsv_stat to "W' and the bill_code to "NOCH"
                # if action == 'A':
                #     print("Add")
                #     rsvstat = 'R'
                #     billcode = "STD"
                # else:
                #     print("Remove")
                #     rsvstat = 'W'
                #     billcode = "NOCH"

                # filepath = settings.ADIRONDACK_CSV_OUTPUT

    except Exception as e:
        print(
                    "Error in adirondack_room_assignments_api.py- Main:  " +
                    e.message)
        # fn_write_error("Error in adirondack_std_billing_api.py - Main: "
        #                + e.message)


if __name__ == "__main__":
    main()
#     args = parser.parse_args()
#     test = args.test
#     database = args.database
#
# if not database:
#     print "mandatory option missing: database name\n"
#     parser.print_help()
#     exit(-1)
# else:
#     database = database.lower()
#
# if database != 'cars' and database != 'train' and database != 'sandbox':
#     print "database must be: 'cars' or 'train' or 'sandbox'\n"
#     parser.print_help()
#     exit(-1)
#
# sys.exit(main())

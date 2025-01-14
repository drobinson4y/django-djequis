import os
import sys
import pysftp
import csv
import codecs
import warnings
from datetime import datetime
import time
from time import strftime
import argparse
import logging
from logging.handlers import SMTPHandler

# django settings for shell environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "djequis.settings")

# prime django
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

from cc_adp_sql import CX_VIEW_SQL, Q_CC_ADP_VERIFY, INS_CC_ADP_REC
from cc_adp_utilities import WRITE_ADP_HEADER, WRITE_HEADER, \
    WRITE_ROW_REFORMATTED, fn_write_error

from djequis.core.utils import sendmail
from djzbar.utils.informix import get_engine
from djzbar.utils.informix import do_sql
from djzbar.settings import INFORMIX_EARL_SANDBOX
from djzbar.settings import INFORMIX_EARL_TEST
from djzbar.settings import INFORMIX_EARL_PROD
from djtools.fields import TODAY
from djequis.adp.utilities import fn_validate_field, fn_format_phone
from djequis.adp.adp_ftp import file_download

# normally set as 'debug" in SETTINGS
DEBUG = settings.INFORMIX_DEBUG

# set up command-line options
desc = """
    Upload ADP data to CX
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

# This is a hack to get rid of a warning message paramico, cryptography
warnings.filterwarnings(action='ignore',module='.*paramiko.*')

#sFTP fetch (GET) downloads the file from ADP file from server

def file_download():
    # print("Get ADP File")
    cnopts = pysftp.CnOpts()
    cnopts.hostkeys = None
    # cnopts.hostkeys = settings.ADP_HOSTKEY
    # External connection information for ADP Application server
    XTRNL_CONNECTION = {
       'host': settings.ADP_HOST,
       'username': settings.ADP_USER,
       'password': settings.ADP_PASS,
       'cnopts': cnopts
    }
    with pysftp.Connection(**XTRNL_CONNECTION) as sftp:
        try:
            # print('Connection Established')
            sftp.chdir("adp/")
            # Remote Path is the ADP server and once logged in we fetch
            # directory listing
            remotepath = sftp.listdir()
            # Loop through remote path directory list
            # print("Remote Path = " + str(remotepath))
            for filename in remotepath:
                remotefile = filename
                # print("Remote File = " + str(remotefile))
                # set local directory for which the ADP file will be
                # downloaded to
                local_dir = ('{0}'.format(
                    settings.ADP_CSV_OUTPUT
                ))
                localpath = local_dir + remotefile
                # GET file from sFTP server and download it to localpath
                sftp.get(remotefile, localpath)
                #############################################################
                # Delete original file %m_%d_%y_%h_%i_%s_Applications(%c).txt
                # from sFTP (ADP) server
                #############################################################
                # sftp.remove(filename)
        except Exception as e:
            # print("Error in cc_adp_rec.py- File download, " + e.message)
            fn_write_error("Error in cc_adp_rec.py - File download, "
                           "adptocx.csv not found, " + e.message)

    sftp.close()


def main():
    # set start_time in order to see how long script takes to execute
    start_time = time.time()

    ##########################################################################
    # ==> python cc_adp_rec.py --database=train --test
    # ==> python cc_adp_rec.py --database=cars
    ##########################################################################

    # # Defines file names and directory location
    new_adp_file = settings.ADP_CSV_OUTPUT + "ADPtoCX.csv"

    last_adp_file = settings.ADP_CSV_OUTPUT + "adptocxview.csv"

    adp_diff_file = settings.ADP_CSV_OUTPUT + "different.csv"

    adptocx_reformatted = settings.ADP_CSV_OUTPUT + "ADPtoCX_Reformatted.csv"

    # First remove yesterdays file of updates
    if os.path.isfile(adp_diff_file):
        os.remove(adp_diff_file)
    # Create new diff file

    try:
        # set global variable
        global EARL
        # determines which database is being called from the command line
        if database == 'cars':
            EARL = INFORMIX_EARL_PROD
        if database == 'train':
            EARL = INFORMIX_EARL_TEST
        elif database == 'sandbox':
            EARL = INFORMIX_EARL_SANDBOX
        else:
            # this will raise an error when we call get_engine()
            # below but the argument parser should have taken
            # care of this scenario and we will never arrive here.
            EARL = None
        # establish database connection
        engine = get_engine(EARL)

        #################################################################
        # STEP 0--
        # Pull the file from the ADP FTP site
        # execute sftp code that needs to be executed in production only
        #################################################################
        if not test:
            file_download()
            # print("file downloaded")

        #################################################################
        # STEP 1--
        # Get the most recent rows from the cc_adp_rec table and write them
        # to a csv file to locate Read files and write out differences
        #################################################################
        WRITE_ADP_HEADER(adptocx_reformatted)

        #################################################################
        # NEW NEW NEW NEW NEW NEW NEW NEW NEW NEW NEW NEW
        # STEP 2--
        # Rewrite the ADP file formatted to match the CX constraints
        # on length and different coding and date format
        #################################################################
        with codecs.open(new_adp_file, 'r',
                         encoding='utf-8-sig') as f:

        # with open(new_adp_file, 'r') as f:
            d_reader = csv.DictReader(f, delimiter=',')
            for row in d_reader:
                WRITE_ROW_REFORMATTED(adptocx_reformatted, row)
        f.close()
        # print("Created Reformatted file")

        #################################################################
        # STEP 3--
        # Instead of using the ADP last file for comparison, use instead
        # the data that is currently in cc_adp_rec so we know we are current
        #################################################################
        WRITE_ADP_HEADER(settings.ADP_CSV_OUTPUT + "adptocxview.csv")
        data_result = engine.execute(CX_VIEW_SQL)
        ret = list(data_result.fetchall())
        # print("SQL Successful")

        with open(last_adp_file, 'a') as file_out:
            csvWriter = csv.writer(file_out, delimiter=',',
                                   dialect='myDialect')
            for row in ret:
                csvWriter.writerow(row)
        file_out.close()

        #################################################################
        # Read in both files and compare
        # the codecs function prevents the header from ADP getting
        # into the comparison - needed because of extra characters in header
        WRITE_HEADER(adp_diff_file)
        with codecs.open(adptocx_reformatted, 'r',
                        encoding='utf-8-sig') as t1, codecs.open(last_adp_file,
                'r', encoding='utf-8-sig') as t2:

            newfile = t1.readlines()
            oldfile = t2.readlines()
            # print("Diff file created")
            # This uses sets to compare the two files
            # returns additions or changes in new but not in original
            bigb = set(newfile) - set(oldfile)

            with open(adp_diff_file, 'a') as file_out:
                for line_no, line in enumerate(bigb):
                    # x = line.split(',')
                    file_out.write(line)

            # close the files
            t1.close()
            t2.close()
            file_out.close()

        #################################################################
        # STEP 4--
        # Open differences file and start loop through records
        #################################################################

        with open(adp_diff_file, 'r') as f:
            d_reader = csv.DictReader(f, delimiter=',')

            try:
                for row in d_reader:
                    # print('carthid = {0}, '
                    #       'Fullname = {1}'.format(row["carth_id"],
                    #                                    row["payroll_name"]))
                    # print('Birthdate = ' + row["birth_date"])
                    if row["carth_id"] == "":
                        SUBJECT = 'No Carthage ID'
                        BODY = "No Carthage ID for " + row['payroll_name']
                        # print("No Carthage ID for " + row['payroll_name'])
                        fn_write_error("No Carthage ID for "
                                       + row['payroll_name'])
                        # sendmail(settings.ADP_TO_EMAIL,
                        # settings.ADP_FROM_EMAIL,
                        #     BODY, SUBJECT
                        # )

                    elif row["file_number"] == "":
                        fn_write_error("No ADP File Number for "
                                       + row['payroll_name'])
                        SUBJECT = 'No ADP File Number'
                        BODY = "No ADP File Number for " + row['payroll_name']
                        # sendmail(settings.ADP_TO_EMAIL,
                        # settings.ADP_FROM_EMAIL,
                        #          BODY, SUBJECT)
                    else:

                        #####################################################
                        # STEP 4a--
                        # Make sure record is not already in cc_adp_rec
                        # Limitations on filtering the ADP report
                        # allow rare cases
                        # of identical rows in report.
                        #####################################################
                        # try:

                        verifyqry = Q_CC_ADP_VERIFY(row)

                        sql_val = do_sql(verifyqry, key=DEBUG, earl=EARL)
                        # print("sql_val = " + str(sql_val))
                        if sql_val is not None:
                            row1 = sql_val.fetchone()
                            if row1 is None:
                                # print("No Matching Record found - Insert")

                                ##############################################
                                # STEP 4b--
                                # Write entire row to cc_adp_rec table
                                ##############################################
                                try:
                                    INS_CC_ADP_REC(row, EARL)
                                    # print("Insert")
                                except Exception as e:
                                    fn_write_error("Error in adptcx.py while "
                                                   "inserting into cc_adp_rec "
                                                   "Error = " + e.message)
                                    continue
                                    # print("ERROR = " + e.message)
                            # else:
                                # print("Found Record - do not insert
                                #       duplicate")
            except Exception as e:
                # print(e.message)
                fn_write_error("Error in cc_adp_rec.py, Error = " + e.message)
                sendmail(settings.ADP_TO_EMAIL, settings.ADP_FROM_EMAIL,
                         "Error in cc_adp_rec.py, Error = " + e.message,
                         "Error in cc_adp_rec.py")

            f.close()

    except Exception as e:
        # print("Error in cc_adp_rec.py, Error = " + e.message)
        fn_write_error("Error in cc_adp_rec.py, Error = " + e.message)
        sendmail(settings.ADP_TO_EMAIL, settings.ADP_FROM_EMAIL,
                 "Error in cc_adp_rec.py, Error = " + e.message,
                 "Error in cc_adp_rec.py")
        # finally:
        #     logging.shutdown()


if __name__ == "__main__":
    args = parser.parse_args()
    test = args.test
    database = args.database

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

sys.exit(main())

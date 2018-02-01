import os
import sys
import pysftp
import csv
import time
import argparse
import shutil

# python path
sys.path.append('/usr/lib/python2.7/dist-packages/')
sys.path.append('/usr/lib/python2.7/')
sys.path.append('/usr/local/lib/python2.7/dist-packages/')
sys.path.append('/data2/django_1.11/')
sys.path.append('/data2/django_projects/')
sys.path.append('/data2/django_third/')

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
os.environ['LD_LIBRARY_PATH'] = settings.LD_LIBRARY_PATH
os.environ['LD_RUN_PATH'] = settings.LD_RUN_PATH

from djequis.sql.schoology import COURSES
from djequis.sql.schoology import USERS
from djequis.sql.schoology import ENROLLMENT
from djequis.core.utils import sendmail
from djzbar.utils.informix import do_sql

EARL = settings.INFORMIX_EARL

desc = """
    Schoology Upload
"""
parser = argparse.ArgumentParser(description=desc)

parser.add_argument(
    "--test",
    action='store_true',
    help="Dry run?",
    dest="test"
)

def main():
    # formatting date and time string 
    datetimestr = time.strftime("%Y%m%d%H%M%S")
    # set dictionary
    dict = {
        'COURSES': COURSES,
        'USERS': USERS,
        'ENROLLMENT': ENROLLMENT
        }
    '''
    # by adding cnopts, I'm authorizing the program to ignore the host key and just continue
    cnopts = pysftp.CnOpts()
    cnopts.hostkeys = None # ignore known hosts
    # sFTP connection information for Schoology
    XTRNL_CONNECTION1 = {
        'host':settings.SCHOOLOGY_HOST,
        'username':settings.SCHOOLOGY_USER,
        'password':settings.SCHOOLOGY_PASS,
        'port':settings.SCHOOLOGY_PORT,
        'cnopts':cnopts
    }
    '''
    for key, value in dict.items():
        print key
        ########################################################################
        # Dict Value 'COURSES' selects......

        # Dict Value 'USERS' selects......

        # Dict Value 'ENROLLMENT' selects......
        ########################################################################
        sql = do_sql(value, earl=EARL)
        rows = sql.fetchall()
        for row in rows:
            print row
        # set directory and filename to be stored
        # ex. /data2/www/data/schoology/COURSES.csv
        filename = ('{0}{1}.csv'.format(
            settings.SCHOOLOGY_CSV_OUTPUT,key
        ))
        # set destination path and new filename that it will be renamed to when archived
        # ex. /data2/www/data/schoology_archives/COURSES_BAK_20180123082403.csv
        archive_destination = ('{0}{1}_{2}_{3}.csv'.format(
            settings.SCHOOLOGY_CSV_ARCHIVED,key,'BAK',datetimestr
        ))
        # create .csv file
        csvfile = open(filename,"w");
        output = csv.writer(csvfile)
        # write header row to file
        if key == 'COURSES': # write header row for COURSES
            output.writerow([
                "Course Name", "Department", "Course Code", "Credits", "Description",
                "Section Name", "Section School Code", "Section Code",
                "Section Description", "Location", "School", "Grading Period"
                ])
        if key == 'USERS': # write header row for USERS
            output.writerow([
                "First Name","Preferred First Name", "Middle Name", "Last Name",
                "Name Prefix", "User Name", "Email", "Unique ID", "Role", "School",
                "Schoology ID", "Position", "Pwd", "Gender", "Graduation Year",
                "Additional Schools" 
            ])
        if key == 'ENROLLMENT': # write header row for ENROLLMENT
            output.writerow([
                "Course Code", "Section Code", "Section School Code", "Unique ID",
                "Enrollment Type", "Grade Period" 
            ])
        if rows is not None:
            for row in rows:
                output.writerow(row)
        else:
            print ("No values in list")
        csvfile.close()
        # renaming old filename to newfilename and move to archive location
        shutil.copy(filename, archive_destination)
    '''
    # set local path {/data2/www/data/barnesandnoble/}
    source_dir = ('{0}'.format(settings.BARNESNOBLE_CSV_OUTPUT))
    # set local path and filenames
    # variable == /data2/www/data/schoology/{filename.csv}
    fileCourses = source_dir + 'COURSES.csv'
    fileUsers = source_dir + 'USERS.csv'
    fileEnrollment = source_dir + 'ENROLLMENT.csv'
    # sFTP PUT moves the EXENCRS.csv file to the Barnes & Noble server 1
    try:
        with pysftp.Connection(**XTRNL_CONNECTION1) as sftp:
            # used for testing
            #sftp.chdir("TestFiles/")
            sftp.put(fileCourses, preserve_mtime=True)
            # deletes original file from our server
            os.remove(fileCourses)
            # closes sftp connection
            sftp.close()
    except Exception, e:
        SUBJECT = 'SCHOOLOGY UPLOAD failed'
        BODY = 'Unable to PUT .csv to Schoology server.\n\n{0}'.format(str(e))
        sendmail(
            settings.SCHOOLOGY_TO_EMAIL,settings.SCHOOLOGY_FROM_EMAIL,
            BODY, SUBJECT
        )
    '''

if __name__ == "__main__":
    args = parser.parse_args()
    test = args.test

    sys.exit(main())
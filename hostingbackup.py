# coding: utf8
"""
https://github.com/RafaTicArte/HostingBackup
"""

import os
from os.path import basename
import sys
import shutil
import configparser
from pathlib import Path
import subprocess
from subprocess import Popen, PIPE
import datetime

import smtplib
import email.message
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

__repository__ = "https://github.com/RafaTicArte/HostingBackup"
__author__ = "Rafa Morales and Jesus Budia"
__version__ = "0.6"
__email__ = "rafa@ticarte.com"
__status__ = "Development"

def delete_local_older(path, days):
    ''' Delete all the directories in path if these directories are older
        that the indicated days.

    Keyword arguments:
    path -- a list with strings for the paths of the directories to copy and compress
    days -- Used to check which directories are older.

    Returns: An error message
    '''
    error_code = 0
    error_message = ""
    current_dir = None

    try:
        p = Path(path)
        #Follow all the elements in the path that are directories
        for dir in p.iterdir():
            if dir.is_dir():
                current_dir = dir
                #Read the time of last modification
                time_modified = datetime.datetime.fromtimestamp(os.stat(dir.as_posix()).st_mtime)
                #Compares with the current time to check if it is old enough to be deleted
                if datetime.datetime.now() - time_modified > datetime.timedelta(days=days):
                    shutil.rmtree(str(dir))
                    error_message += "(OK) " + str(current_dir) + "\n"
    except OSError:
        error_code = 1
        error_message += "(ERROR) " + str(current_dir) + "\n"

    return error_code, error_message


def copy_structure(directories, targetPath, tar_system, command_path):
    ''' Copy directories with subdirectories and files and compress them in a tar file

    Keyword arguments:
    directories -- a list with tuples with strings for the paths of the directories to copy and compress and the names of the compressed files
    targetPath -- the path where the tar files will be created
    tar_system -- compress with system executable
    command_path -- the path of the command to be executed if tar_system is true

    Important: Omit the last slash in the path when using this function

    Returns: An error message and a correct message
    '''
    error_code = 0
    error_message = ""
    for name, directory in directories:
        try:
            if os.path.exists(directory):
                #Extract the relevant parts of the path
                base_dir = os.path.basename(directory)
                parent_dir = Path(directory).parent

                path = os.path.join(targetPath, name)

                #Casting for 3.5.3 Compatible
                base_dir = str(base_dir)
                parent_dir = str(parent_dir)
                path = str(path)

                #Make the tar file
                if tar_system:
                    args = [command_path, "czf", targetPath+"/"+name+".tar.gz", directory]
                    output = subprocess.check_output(args, stderr=subprocess.STDOUT, universal_newlines=True)
                else:
                    shutil.make_archive(path, "gztar", parent_dir, base_dir)

                error_message += "(OK) " + directory + " (" + str(round(os.path.getsize(targetPath+"/"+name+".tar.gz")/1024/1024)) + "MB)\n"
            else:
                error_code = 1
                error_message += "(ERROR) " + directory + " does not exist\n"
        except OSError as e:
            error_code = 2
            error_message += "(ERROR) " + directory + " " + e.strerror + "\n"
        except subprocess.CalledProcessError as e:
            error_code = 1
            error_message += "(ERROR) " + e.output.rstrip("\n") + "\n"

    return error_code, error_message


def export_db(alias, user, password, host, port, database, targetPath, excludes, command_path):
    ''' Export database using the current configuration

    Keyword arguments:
    alias -- the name for the dumped file
    user -- the user to connect to the database
    password -- the password to connect to the database
    host -- the host of the database
    database -- a string with the names of the database to export
    targetPath -- the path of the backup file that will be created
    excludes -- a list containing all the tables to be excluded
    command_path -- the path of the command to be executed

    Returns: An error code and error message.
    '''
    error_code = 0
    error_message = ""

    try:
        targetPath_final = os.path.join(targetPath, alias + ".sql")

        #Create a list containing all the parameters
        #--force: continue with errors
        args = [command_path, "--single-transaction", "-u", user, "--port", port, "-p"+password, "-h", host, "--force", database]
        args.extend(["--result-file", targetPath_final])
        #Specifies which tables will be excluded
        for table in excludes:
            args.extend(["--ignore-table" , database + "." + table])

        #Execute the command
        process = subprocess.check_output(args, stderr=subprocess.STDOUT, universal_newlines=True)

        error_message += "(OK) " + alias + "\n"

    except subprocess.CalledProcessError as e:
        error_code = 1
        error_message += "(ERROR) " + alias + " " + e.output.rstrip("\n") + "\n"

    return error_code, error_message


def check_db_size(alias, user, password, host, port, database, max_size, command_path):
    ''' Checks if the size of a database has reached some maximum size

    Keyword arguments:
    user -- the user to connect to the database
    password -- the password to connect to the database
    host -- the host of the database
    database -- the database whose size will be checked
    max_size -- the limit that must be not limit_reached in MB
    command_path -- the path to the executable

    Returns: A tuple containing a boolean and a error message.
    The boolean limit_reached will be True if the current size of the database
    checked is greater than the max_size.
    '''
    error_code = 0
    error_message = ""

    try:
        #Form the query
        query = '''SELECT table_schema AS "Database", SUM(data_length + index_length)/1024/1024 AS "Size in MB"
        FROM information_schema.TABLES
        WHERE table_schema='{database}'
        GROUP BY table_schema;'''.format(database=database)

        args = [command_path, "-u", user, "-p"+password, "-h", host, "--port", port, "-e", query]
        #Execute the query to check the size of the specified database
        output = subprocess.check_output(args, stderr=subprocess.STDOUT, universal_newlines=True)

        #Strip the content of the string to get the numeric value and discard the rest
        for line in output.splitlines():
            if line.rsplit('\t')[0] == database:
                current_size = float(line.rsplit('\t')[1])

        #Checks if the current size is greater than the configured maximum size
        if current_size > int(max_size):
            error_code = 1
            error_message +=  "(ERROR_SIZE) "+ alias + " (" + str(int(current_size)) + "MB)" + "\n"
        else:
            error_message += "(OK) " + alias + " (" + str(int(current_size)) + "MB)" + "\n"

    except subprocess.CalledProcessError as e:
        error_code = 2
        error_message += "(ERROR) " + alias + " " + e.output.rstrip("\n") + "\n"

    return error_code, error_message


def list_gdrive_older(parent, days, command_path):
    ''' List files and directories that are older than days.

    Keyword arguments:
    parent -- the code/id of the parent directory, run gdrive --list to discover the
              right code.
    days -- used to filter the files whose last modification was previous to a date
    command_path -- the path to the executable

    Returns: An tuple containing a list of directory ids and an error code and message
    '''
    error_code = 0
    error_message = ""
    ids = []
    date_formated = time_ago(days)
    query = "'" + parent + "' " + "in parents and trashed = false and modifiedTime < "
    query += "'" + date_formated  + "'"
    args = [command_path, "list", "--query", query, "-m", "10000"]
    #Execute the query to list the directories that fullfill the filter
    try:
        output = subprocess.check_output(args, stderr=subprocess.STDOUT, universal_newlines=True)

        #Strips the unnecessary data, we just need the codes for the directories
        lines = output.splitlines()[1:]
        ids = [line.split(" ")[0] for line in lines]

    except subprocess.CalledProcessError as e:
        error_code = 1
        error_message += "(ERROR) GDrive list: " + e.output.rstrip("\n") + "\n"

    return error_code, error_message, ids


def delete_gdrive_directories(directories_ids, command_path):
    ''' Delete some directories in google drive based on the ids.

    Keyword arguments:
    directories_ids -- A list with the ids of the directories to delete
    command_path -- the path to the executable

    Returns: An error message
    '''
    error_code = 0
    error_message = ""
    for id in directories_ids:
        args = [command_path, "delete", "--recursive", id]
        #Execute the query to list the directories that fullfill the filter
        try:
            output = subprocess.check_output(args, stderr=subprocess.STDOUT, universal_newlines=True)
            error_message += "(OK) " + str(output) + "\n"

        except subprocess.CalledProcessError as e:
            error_code = 1
            error_message += "(ERROR) " + e.output.rstrip("\n") + "\n"

    return error_code, error_message


def delete_rclone_older(parent, days, command_path):
    ''' Delete some directories in google drive based on the ids.

    Keyword arguments:
    parent -- remote directory
    days -- Keep days
    command_path -- the path to the executable

    Returns: An error message
    '''
    error_code = 0
    error_message = ""
    
    #Execute the query to list the directories
    try:
        args = [command_path, "lsd", parent]
        output = subprocess.check_output(args, stderr=subprocess.STDOUT, universal_newlines=True)

        #Strips the unnecessary data, we just need the codes for the directories
        args = [command_path, "purge", parent]
        lines = output.splitlines()[1:]
        for line in lines:
            dir_name = line.split()[4]
            dir_date = datetime.datetime.strptime(dir_name.split("-")[0], '%Y%m%d')
            dir_date_diff = (datetime.datetime.now().date() - dir_date.date()).days
            if (dir_date_diff > days):
                args = [command_path, "purge", parent + "/" + dir_name]
                output = subprocess.check_output(args, stderr=subprocess.STDOUT, universal_newlines=True)
                error_message += "(OK) " + dir_name + "\n"

    except subprocess.CalledProcessError as e:
        error_code = 1
        error_message += "(ERROR) RClone delete: " + e.output.rstrip("\n") + "\n"

    return error_code, error_message


def upload_gdrive(path, parent, command_path):
    ''' Uploads a directory to google drive.

    Keyword arguments:
    path -- the directory to upload
    parent -- the code of the parent directory, run gdrive --list to discover the
              right code.
    command_path -- the path to the executable

    Returns: An error message
    '''
    error_code = 0
    error_message = ""

    args = [command_path, "upload", "--recursive", "--no-progress", "-p", parent, path]
    try:
        #Execute the command to upload the directory
        output = subprocess.check_output(args, stderr=subprocess.STDOUT, universal_newlines=True)

        error_message += "(OK)\n" + str(output)

    except subprocess.CalledProcessError as e:
        error_code = 1
        error_message += "(ERROR) " + e.output.rstrip("\n") + "\n"

    return error_code, error_message


def upload_rclone(path_local, path_remote, command_path):
    ''' Uploads a directory to google drive.

    Keyword arguments:
    path_local -- the directory to upload
    path_remote -- the code of the parent directory, run gdrive --list to discover the
              right code.
    command_path -- the path to the executable

    Returns: An error message
    '''
    error_code = 0
    error_message = ""

    args = [command_path, "copy", path_local, path_remote]
    try:
        #Execute the command to upload the directory
        output = subprocess.check_output(args, stderr=subprocess.STDOUT, universal_newlines=True)

        error_message += "(OK)\n" + str(output)

    except subprocess.CalledProcessError as e:
        error_code = 1
        error_message += "(ERROR) " + e.output.rstrip("\n") + "\n"

    return error_code, error_message


def send_mail_smtp(subject, send_from, send_to, body, smtp_server, port, user, passw, files=None, TLS=True):
    ''' Sends an email by smtp with the specified data

    Keyword arguments:
    subject -- the subject of the message
    send_from -- the sender of the message
    send_to -- the receiver of the message
    body -- the body of the message (it can contains html tags)
    smtp_server -- domain of the server
    port -- port of the smtp server
    user -- email of the sender for authentication
    passw -- password for authentication
    files -- a list of path of files to be attached (optional)
    TLS -- to decide if use TLS or SSL as encrytion mechanism (default to true)

    Returns: An error message.
    '''
    error_message = ""
    timeout = False
    #Create the message
    msg = email.message.EmailMessage()
    msg['Subject'] = subject
    msg['From'] = send_from
    msg['To'] = send_to
    #Set the type to html
    msg.add_header('Content-Type','text/html')
    msg.set_payload(body)

    #Attach files
    msg.make_mixed()
    for f in files or []:
        try:
            with open(f, "rb") as fil:
                part = MIMEApplication(

                    fil.read(),
                    Name=basename(f)
                )
            # When the file is closed is attached to the message
            part['Content-Disposition'] = 'attachment; filename="%s"' % basename(f)
            msg.attach(part)
        except OSError:
            error_message += "No se encontró o no se pudo abrir el archivo: " + f + "\n"

    #Create the connection (TLS or SSL)
    if TLS:
        try:
            smtpObj = smtplib.SMTP(smtp_server, port, timeout=20)
        except OSError:
            error_message += "Se excedió el tiempo de espera." + "\n"
            timeout = True
    else:
        try:
            smtpObj = smtplib.SMTP_SSL(smtp_server, port, timeout=20)
        except OSError:
            error_message += "Se excedió el tiempo de espera." + "\n"
            timeout = True

    #If the limit time hasn't passed
    if not timeout:
        smtpObj.ehlo()
        if TLS:
            smtpObj.starttls()

        #Login to authenticate with the mail server
        try:
            smtpObj.login(user, passw)
        except smtplib.SMTPAuthenticationError:
            error_message += "Error de autentificación. Comprueba usuario y contraseña." + "\n"

        #Send the mail
        try:
            smtpObj.sendmail(msg['From'], [msg['To']], msg.as_string().encode('utf-8'))
        except smtplib.SMTPSenderRefused:
            error_message += "El servidor de correo rechazó la conexión." + "\n"
        #Close the connection
        smtpObj.quit()

    return(error_message)


def send_mail_sendmail(subject, send_from, send_to, body, command_path):
    ''' Sends an email by sendmail with the specified data

    Keyword arguments:
    subject -- the subject of the message
    send_from -- the sender of the message
    send_to -- the receiver of the message
    body -- the body of the message (it can contains html tags)

    Returns: An error message.
    '''
    error_message = ""

    msg = MIMEMultipart('alternative')
    msg["From"] = send_from
    msg["To"] = send_to
    msg["Subject"] = subject
    msg.attach( MIMEText(body, 'html', 'UTF-8') )

    process = Popen([command_path, "-t", "-oi"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    stdout, stderr = process.communicate(msg.as_string())

    if process != 0:
        error_message = stderr

    return(error_message)


def time_ago(days):
    ''' Calculate the date of N days ago and format the result.

    Keyword arguments:
    days -- How many days ago

    Returns: The calculated date with a proper format
    '''
    date_N_days_ago = datetime.datetime.now() - datetime.timedelta(days=days)
    return date_N_days_ago.strftime("%Y-%m-%dT00:00:00")


def output_format(element, message=''):
    ''' Change message to HTML format.

    Keyword arguments:
    element -- HTML element
    message -- String to format

    Returns: String with HTML format
    '''
    if element == 'table-open':
        return '<table style="font-family: Helvetica; font-size: 1.1em; line-height: 1.4; border-collapse: collapse; width: 100%; background-color: #fff;">'
    elif element == 'table-close':
        return '</table>'
    elif element == 'caption':
        return '<caption style="font-size: 1.2em; font-weight: bold; font-variant: small-caps; padding: 5px;">' + message + '</caption>'
    elif element == 'row-header':
        return '<tr style="color: #fff; text-transform: uppercase; background-color: #36304a;"><td style="padding: 10px;">' + message + '</td></tr>'
    elif element == 'row-action':
        return '<tr style="color: gray; background-color: #f2f2f2;"><td style="padding: 10px;">' + message + '</td></tr>'
    elif element == 'row':
        return '<tr style="color: #2b2b2b;"><td style="padding: 5px 10px">' + message + '</td></tr>'
    elif element == 'version':
        return '<p style="color: gray; font-size: 0.8em;">' + __repository__ + ' [version: ' + __version__ + ']</p>'

#Main Script
if __name__ == "__main__":
    #To keep count of any failure
    success = True
    #Error code and message
    error_code = 0
    error_message = ""

    #Load and read the configuration
    config = configparser.ConfigParser()
    #Keep case sensitive
    config.optionxform = str
    #This script must be called with an argument containing the path to the configuration file.
    config.read(sys.argv[1], encoding='utf8')

    #Create basic tools
    local_dir = config['general']['local_dir']
    now = datetime.datetime.now()
    joined_dir = None

    #Create the path for the log file
    logfile_path = os.path.join(local_dir, os.path.basename(sys.argv[1]) + ".log")
    #Delete the log file at the start to empty their contents
    if os.path.exists(logfile_path):
        os.remove(logfile_path)
    #Create the log file if doesn't exist
    log = open(logfile_path, 'a', encoding='utf8')

    #Start backup
    log.write(output_format('table-open'))
    log.write(output_format('caption', "Registro de actividad"))
    log.write(output_format('row-header', "Inicio: " + now.strftime("%d-%m-%Y %H:%M:%S")))

    if config['actions'].getboolean('delete_old_local_action'):
        now = datetime.datetime.now()
        log.write(output_format('row-action', "Eliminando copias antiguas locales: " + now.strftime("%H:%M:%S")))
        days = int(config['general']['days_old_local'])
        error_code, error_message = delete_local_older(local_dir, days)
        if error_code != 0:
            success = False
        log.write(output_format('row', error_message))

    if config['actions'].getboolean('delete_old_gdrive_action'):
        now = datetime.datetime.now()
        log.write(output_format('row-action', "Eliminando copias antiguas Google Drive: " + now.strftime("%H:%M:%S")))
        days = int(config['general']['days_old_gdrive'])
        parent = config['general']['gdrive_dir']
        command_path = config['executables']['gdrive']
        error_code, error_message, dir_ids = list_gdrive_older(parent, days, command_path)
        if error_code != 0:
            success = False
        else:
            error_code, error_message = delete_gdrive_directories(dir_ids, command_path)
            if error_code != 0:
                success = False
        log.write(output_format('row', error_message))

    if config['actions'].getboolean('delete_old_rclone_action'):
        now = datetime.datetime.now()
        log.write(output_format('row-action', "Eliminando copias antiguas Google Drive: " + now.strftime("%H:%M:%S")))
        days = int(config['general']['days_old_gdrive'])
        parent = config['general']['rclone_dir']
        command_path = config['executables']['rclone']
        error_code, error_message = delete_rclone_older(parent, days, command_path)
        log.write(output_format('row', error_message))

    if config['actions'].getboolean('copy_structure_action') or config['actions'].getboolean('export_db_action'):
        #Create a directory with the current datetime like name
        now = datetime.datetime.now()
        new_dir = now.strftime("%Y%m%d-%H%M%S")
        joined_dir = os.path.join(local_dir, new_dir)
        os.makedirs(joined_dir)

    if config['actions'].getboolean('copy_structure_action'):
        now = datetime.datetime.now()
        log.write(output_format('row-action', "Comprimiendo directorios: " + now.strftime("%H:%M:%S")))
        directories = config['directories'].items()
        tar_system = config['general'].getboolean('tar_system')
        command_path = config['executables']['tar']
        error_code, error_message = copy_structure(directories, joined_dir, tar_system, command_path)
        if error_code != 0:
            success = False
        log.write(output_format('row', error_message))

    if config['actions'].getboolean('export_db_action'):
        now = datetime.datetime.now()
        log.write(output_format('row-action', "Exportando bases de datos: " + now.strftime("%H:%M:%S")))
        full_error = ""
        for section in config.sections():
            if "database" in section and config[section].getboolean('export'):
                user = config[section]['user']
                password = config[section]['password']
                host = config[section]['host']
                port = config[section]['port']
                database = config[section]['name']
                targetPath = joined_dir
                command_path = config['executables']['mysqldump']
                excludes = []
                for key in config[section].keys():
                    #Create a list containing all the tables to exclude
                    if "exclude" in key:
                        excludes.append(config[section][key])
                alias = config[section]['alias']
                error_code, error_message = export_db(alias, user, password, host, port, database, targetPath, excludes, command_path)
                if error_code != 0:
                    success = False
                log.write(output_format('row', error_message))

    if config['actions'].getboolean('check_db_size_action'):
        now = datetime.datetime.now()
        log.write(output_format('row-action', "Comprobando tamaño bases de datos: " + now.strftime("%H:%M:%S")))
        command_path = config['executables']['mysql']
        #Checks all the databases configured
        for section in config.sections():
            if "database" in section and config[section].getboolean('check'):
                alias = config[section]['alias']
                database = config[section]['name']
                max_size = config[section]['size']
                user = config[section]['user']
                password = config[section]['password']
                host = config[section]['host']
                port = config[section]['port']
                error_code, error_message = check_db_size(alias, user, password, host, port, database, max_size, command_path)

                if error_code != 0:
                    success = False
                log.write(output_format('row', error_message))

    if config['actions'].getboolean('upload_gdrive_action'):
        now = datetime.datetime.now()
        log.write(output_format('row-action', "Subiendo copias a Google Drive: " + now.strftime("%H:%M:%S")))
        parent = config['general']['gdrive_dir']
        command_path = config['executables']['gdrive']
        error_code, error_message = upload_gdrive(joined_dir, parent, command_path)
        if error_code != 0:
            success = False
        log.write(output_format('row', error_message))

    if config['actions'].getboolean('upload_rclone_action'):
        now = datetime.datetime.now()
        log.write(output_format('row-action', "Subiendo copias a Google Drive: " + now.strftime("%H:%M:%S")))
        parent = config['general']['rclone_dir'] + "/" + new_dir
        command_path = config['executables']['rclone']
        error_code, error_message = upload_rclone(joined_dir, parent, command_path)
        if error_code != 0:
            success = False
        log.write(output_format('row', error_message))

    #Close the log file
    now = datetime.datetime.now()
    log.write(output_format('row-header', "Fin: " + now.strftime("%d-%m-%Y %H:%M:%S")))
    log.write(output_format('table-close'))
    log.write(output_format('version'))
    log.close()

    #Copy the log file in current backup directory
    if config['actions'].getboolean('copy_structure_action') or config['actions'].getboolean('export_db_action'):
        shutil.copy(logfile_path, joined_dir)

    #Send email
    if config['actions']['send_email_action'] == 'Always' or (config['actions']['send_email_action'] == 'OnlyError' and not success):
        if success:
            subject = config['email']['subject'] + " (OK)"
        else:
            subject = config['email']['subject'] + " (ERROR)"

        log = open(logfile_path, 'r', encoding='utf8')
        body = log.read()
        log.close()
        #Format for html
        body = body.replace("\n", "<br>")

        if config['email']['method'] == 'smtp':
            user = config['email']['email_sender']
            send_from = user
            send_to = config['email']['email_receiver']
            smtp_server = config['email']['smtp_server']
            port = config['email']['port']
            passw = config['email']['password']
            TLS = config['email'].getboolean('TLS')
            error = send_mail_smtp(subject, send_from, send_to, body, smtp_server, port, user, passw, files=None, TLS=True)
        elif config['email']['method'] == 'sendmail':
            send_from = config['email']['email_sender']
            send_to = config['email']['email_receiver']
            command_path = config['executables']['sendmail']
            error = send_mail_sendmail(subject, send_from, send_to, body, command_path)

        sys.stdout.write(error)

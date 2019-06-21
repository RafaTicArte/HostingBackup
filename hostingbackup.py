import os
import sys
import shutil
import configparser
from pathlib import Path
import subprocess
from subprocess import Popen, PIPE
import datetime

import smtplib
from os.path import basename
import email.message
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart


def export_db(user, password, host, port, database, targetPath, command_path, excludes):
    ''' Export the databases using the current configuration

    Keyword arguments:
    user -- the user to connect to the database
    password -- the password to connect to the database
    host -- the host of the database
    database -- a string with the names of the database to export
    targetPath -- the path of the backup file that will be created
    command_path -- the path of the command to be executed
    excludes -- a list containing all the tables to be excluded

    Returns: An error message and a correct message.
    '''
    error_message = ""
    correct_message = ""

    try:
        targetPath_final = os.path.join(targetPath, database + ".sql")
        #Create a list containing all the parameters
        args = [command_path, "-u", user, "--port", port, "-p"+password, "-h", host, database]

        args.extend(["--result-file", targetPath_final])
        #Specifies which tables will be excluded
        for table in excludes:
            args.extend(["--ignore-table" , database + "." + table])

        #Execute the command
        output = subprocess.check_output(args, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        error_message += "Error al exportar la bases de datos " + database + "\n"
        error_message += e.output.decode() + "\n"

    return error_message


def check_db_size(user, password, host, port, database, max_size, command_path):
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

    error_message = ""
    limit_reached = False

    try:
        #Form the query
        query = '''SELECT table_schema "database", sum(data_length + index_length)/1024/1024
        "size in MB" FROM information_schema.TABLES WHERE table_schema='{database}'
        GROUP BY table_schema;'''.format(database=database)
        args = [command_path, "-u", user, "-p"+password, "-h", host, "--port", port, "-e", query]
        #Execute the query to check the size of the specified database
        output = subprocess.check_output(args, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        #Assign the null value because there isn't output
        output = None
        error_message += "Error al comprobar el tamaño de la base de datos: " + database +"\n"
        error_message += e.output.decode() + "\n"

    if output:
        #Strip the contents of the string to get the numeric value and discard the rest
        lines = [line for line in output.decode().splitlines()]
        #Strip the headers
        current_size = float(lines[1].rsplit('\t')[1])

        #Checks if the current size is greater than the configured maximum size
        if current_size > int(max_size):
            limit_reached = True
    else:
        error_message += "Error al comprobar el tamaño de la base de datos: " + database +"\n"

    return (limit_reached, error_message)


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

    msg = email.message.EmailMessage()
    msg["From"] = send_from
    msg["To"] = send_to
    msg["Subject"] = subject
    msg.add_header('Content-Type','text/html')
    msg.set_payload(body)
    sendmailprocess = Popen([command_path, "-t", "-oi"], stdin=PIPE, universal_newlines=True)
    sendmailprocess.communicate(msg.as_string())

    return(error_message)


def copy_structure(directories, destiny):
    ''' Copy directories with subdirectories and files and compress them in a tar file

    Keyword arguments:
    directories -- a list with tuples with strings for the paths of the directories to copy and compress and the names of the compressed files
    destiny -- the path where the tar files will be created

    Important: Omit the last slash in the path when using this function

    Returns: An error message and a correct message
    '''
    error_message = ""
    correct_message = ""
    for name, directory in directories:
        try:
            if os.path.exists(directory):
                #Extract the relevant parts of the path
                base_dir = os.path.basename(directory)
                parent_dir = Path(directory).parent

                path = os.path.join(destiny, name)

                #Casting for 3.5.3 Compatible
                base_dir = str(base_dir)
                parent_dir = str(parent_dir)
                path = str(path)

                #Make the tar file
                shutil.make_archive(path, "gztar", parent_dir, base_dir)
                correct_message += "Se copió correctamente el directorio: " + directory + "\n"
            else:
                error_message += "Error no se encontró el directorio: " + directory + "\n"
        except OSError:
            error_message += "Error no se encontró el directorio: " + directory + "\n"

    return (error_message, correct_message)


def delete_local_old(path, days):
    ''' Delete all the directories in path if these directories are older
        that the indicated days.

    Keyword arguments:
    path -- a list with strings for the paths of the directories to copy and compress
    days -- Used to check which directories are older.

    Returns: An error message
    '''
    error_message = ""
    current_dir = None
    try:
        p = Path(path)
        #Follow all the elements in the path that are directories
        for dir in p.iterdir():
            if dir.is_dir():
                current_dir = dir
                #Read the time of last modification
                time_modified = datetime.datetime.fromtimestamp(os.stat(path).st_mtime)
                #Compares with the current time to check if it is old enough to be deleted
                if datetime.datetime.now() - time_modified > datetime.timedelta(days=days):
                    shutil.rmtree(str(dir))
    except OSError:
        error_message += "No se pudo borrar el directorio: " + current_dir + "\n."

    return error_message


def upload_gdrive(path, parent, command_path):
    ''' Uploads a directory to google drive.

    Keyword arguments:
    path -- the directory to upload
    parent -- the code of the parent directory, run gdrive --list to discover the
              right code.
    command_path -- the path to the executable

    Returns: An error message
    '''
    error_message = ""

    args = [command_path, "upload", "--recursive", "-p", parent, path]
    #Execute the command to upload the directory
    output = subprocess.check_call(args, stderr=subprocess.STDOUT)
    #Checks the return code to inform of an error
    if not output == 0:
        error_message += "Se produjo un error al subir a google drive"

    return error_message

def list_gdrive_older(parent, days, command_path):
    ''' Uploads a directory to google drive.

    Keyword arguments:
    parent -- the code/id of the parent directory, run gdrive --list to discover the
              right code.
    days -- used to filter the files whose last modification was previous to a date
    command_path -- the path to the executable

    Returns: An tuple containing a list of directory ids and an error message
    '''
    error_message = ""
    ids = []
    date_formated = time_ago(days)
    query = "'" + parent + "' " + "in parents and trashed = false and modifiedTime < "
    query += "'" + date_formated  + "'"
    args = [command_path, "list", "--query", query, "-m", "10000"]
    #Execute the query to list the directories that fullfill the filter
    try:
        output = subprocess.check_output(args, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        error_message += "Error al intentar recuperar los directorios antiguos en Gdrive.\n"
        error_message += e.output.decode() + "\n"
    #Checks the output
    #Strips the unnecessary data, we just need the codes for the directories
    if not error_message:
        lines = output.decode().splitlines()[1:]
        ids = [line.split(" ")[0] for line in lines]
    return (ids, error_message)

def time_ago(days):
    ''' Calculate the date of N days ago and format the result.

    Keyword arguments:
    days -- How many days ago

    Returns: The calculated date with a proper format
    '''
    error_message = ""
    date_N_days_ago = datetime.datetime.now() - datetime.timedelta(days=days)
    return date_N_days_ago.strftime("%Y-%m-%dT00:00:00")


def delete_gdrive_directories(directories_ids, command_path):
    ''' Delete some directories in google drive based on the ids.

    Keyword arguments:
    directories_ids -- A list with the ids of the directories to delete
    command_path -- the path to the executable

    Returns: An error message
    '''
    error_message = ""
    for id in directories_ids:
        args = [command_path, "delete", "--recursive", id]
        #Execute the query to list the directories that fullfill the filter
        try:
            output = subprocess.check_output(args, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            error_message += "Error al intentar borrar los directorios en Gdrive.\n"
            error_message += e.output.decode() + "\n"
    return error_message

#Main Script
if __name__ == "__main__":
    #To keep count of any failure
    success = True
    #Load and read the configuration
    config = configparser.ConfigParser()
    #Keep case sensitive
    config.optionxform = str
    #This script must be called with an argument containing the path to the configuration
    #file.
    config.read(sys.argv[1], encoding='utf8')

    #Create basic tools
    local_dir = config['general']['local_dir']
    now = datetime.datetime.now()
    joined_dir = None
    #Create the path for the log file
    logfile_path = os.path.join(local_dir, "backup.log")

    #Deletes the log file at the start to empty their contents
    if os.path.exists(logfile_path):
        os.remove(logfile_path)
    #Create the log file if doesn't exist
    log = open(logfile_path, 'a', encoding='utf8')
    log.write("Registro de actividad: \n")
    log.write("Fecha y hora de inicio: " + now.strftime("%Y-%m-%d %H:%M:%S")  + "\n" + "\n")


    if config['actions'].getboolean('export_db_action') or config['actions'].getboolean('copy_structure_action'):
        #Create a directory with the current datetime like name
        new_dir = now.strftime("%Y%m%d-%H%M%S")
        joined_dir = os.path.join(local_dir, new_dir)
        os.makedirs(joined_dir)

    if config['actions'].getboolean('export_db_action'):
        log.write("Exportando bases de datos: \n")
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
                error = export_db(user, password, host, port, database, targetPath, command_path, excludes)
                full_error += error
        if full_error:
            log.write(full_error)
            success = False
        else:
            log.write("Todas las bases de datos se exportaron correctamente.\n")

    if config['actions'].getboolean('copy_structure_action'):
        log.write("Copiando directorios de forma local: \n")
        directories = config['directories'].items()
        (error, correct) = copy_structure(directories, joined_dir)
        if error:
            log.write(error)
            success = False

        log.write(correct + "\n")

    if config['actions'].getboolean('delete_old_local_action'):
        log.write("Borrando copias antiguas de forma local: \n")
        days = int(config['general']['days_old_local'])
        error = delete_local_old(local_dir, days)
        if error:
            log.write(error)
            success = False
        else:
            log.write("Todos los directorios borrados correctamente.\n")
        log.write("\n")

    if config['actions'].getboolean('delete_old_gdrive_action'):
        log.write("Borrando copias antiguas de Google Drive: \n")
        days = int(config['general']['days_old_gdrive'])
        parent = config['general']['parent']
        command_path = config['executables']['gdrive']
        (dir_ids, error) = list_gdrive_older(parent, days, command_path)
        if error:
            #Abort
            log.write(error)
            success = False
        else:
            error = delete_gdrive_directories(dir_ids, command_path)
            if error:
                log.write(error)
                success = False
            else:
                log.write("Borradas con éxito.\n")
        log.write("\n")

    if config['actions'].getboolean('upload_gdrive_action'):
        log.write("Subiendo copia a Google Drive: \n")
        parent = config['general']['parent']
        command_path = config['executables']['gdrive']
        error = upload_gdrive(joined_dir, parent, command_path)
        if error:
            log.write(error)
            success = False
        else:
            log.write("Correcto: Subida a Google Drive.\n")
        log.write("\n")

    if config['actions'].getboolean('check_db_size_action'):
        command_path = config['executables']['mysql']
        #Total errors concatenated
        error_aux = ""
        limit_aux = ""
        correct_size = ""

        log.write("Comprobando tamaño de base de datos: " +"\n")
        #Checks all the databases configured
        for section in config.sections():
            if "database" in section and config[section].getboolean('check'):
                database = config[section]['name']
                max_size = config[section]['size']
                user = config[section]['user']
                password = config[section]['password']
                host = config[section]['host']
                port = config[section]['port']
                (limit_reached, error) =check_db_size(user, password, host, port, database, max_size, command_path)

                if limit_reached and not error:
                    limit_aux += "La base de datos " + database + " superó el límite de " + max_size + " MB \n"
                if error:
                    error_aux += error
                if not error and not limit_reached:
                    correct_size += "La base de datos " + database + " tiene un tamaño correcto. \n"

        log.write(correct_size)
        log.write(limit_aux)
        log.write(error_aux)

        if error_aux:
            success = False

        #Sends the email just if there was an error, or a limit was reached
        if (limit_aux or error_aux) and not config['actions'].getboolean('send_email_action'):
            subject = "Aviso: Comprobación de tamaño de bases de datos."
            body = correct_size +  limit_aux + error_aux
            #Format for html
            body = body.replace("\n", "<br>")
            user = config['email']['email_sender']
            send_from = user
            send_to = config['email']['email_receiver']
            smtp_server = config['email']['smtp_server']
            port = config['email']['port']
            passw = config['email']['password']
            TLS = config['email'].getboolean('TLS')

            send_mail_smtp(subject, send_from, send_to, body, smtp_server, port, user, passw, files=None, TLS=True)



    #Close the log file
    now = datetime.datetime.now()
    log.write(">>>>>>>>>>>>>>>>>>>" + "\n")
    log.write("Fecha y hora de fin: " + now.strftime("%Y-%m-%d %H:%M:%S")  + "\n" + "\n")
    log.close()

    if config['actions'].getboolean('send_email_action'):
        if success:
            subject = "OK"
        else:
            subject = "ERROR"

        log = open(logfile_path, 'r', encoding='utf8')
        body = log.read()
        #Format for html
        body = body.replace("\n", "<br>")
        log.close()

        if config['email']['method'] == 'smtp':
            user = config['email']['email_sender']
            send_from = user
            send_to = config['email']['email_receiver']
            smtp_server = config['email']['smtp_server']
            port = config['email']['port']
            passw = config['email']['password']
            TLS = config['email'].getboolean('TLS')
            send_mail_smtp(subject, send_from, send_to, body, smtp_server, port, user, passw, files=None, TLS=True)
        elif config['email']['method'] == 'sendmail':
            send_from = config['email']['email_sender']
            send_to = config['email']['email_receiver']
            send_mail_sendmail(subject, send_from, send_to, body, config['executables']['sendmail'])

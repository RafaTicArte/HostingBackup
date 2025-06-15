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

__repository__ = "https://www.ticarte.com/hostingbackup"
__author__ = "Rafa Morales and Jesús Budia"
__version__ = "1.3"
__email__ = "rafa@ticarte.com"
__status__ = "Development"


def delete_dirs_local(dirs_local, days):
    """ Delete all the local directories if these directories are older
        that the indicated days.

    Keyword arguments:
    dirs_local -- List with directories where delete old directories.
    days -- Min days to keep directory.

    Returns: An error code and error message.
    """
    error_code = 0
    error_message = ""
    dir_date = ""

    for dir in Path(dirs_local).iterdir():
        try:
            if dir.is_dir():
                dir_date = datetime.datetime.fromtimestamp(os.stat(dir.as_posix()).st_mtime)
                if (datetime.datetime.now() - dir_date) > datetime.timedelta(days=days):
                    shutil.rmtree(str(dir))
                    error_message += "(OK) " + str(dir) + "\n"
        except OSError:
            error_code = 1
            error_message += "(ERROR) " + str(dir) + "\n"

    return error_code, error_message


def compress_dirs_local(dirs_local, target_dir, compress_method, command_path):
    """ Compress directories, one by one, in a .tar.gz file.

    Keyword arguments:
    dir_locals -- List with directories to compress and names of the compressed files.
    target_dir -- Directory where the compressed files will be created.
    compress_method -- Compress method: Python library (default) or Tar program.
    command_path -- Path of the command to be executed if tar_system is true.

    Important: Omit the last slash in the path when using this function.

    Returns: An error code and error message.
    """
    error_code = 0
    error_message = ""
    for name, dir in dirs_local:
        try:
            if os.path.exists(dir):
                base_dir = os.path.basename(dir)
                parent_dir = Path(dir).parent
                targz_file = os.path.join(target_dir, name)

                # Casting for 3.5.3 compatibility
                base_dir = str(base_dir)
                parent_dir = str(parent_dir)
                targz_file = str(targz_file)

                if compress_method == "Tar":
                    process_args = [command_path, "czf", targz_file + ".tar.gz", dir]
                    process_output = subprocess.check_output(process_args, stderr=subprocess.STDOUT,
                                                             universal_newlines=True)
                else:
                    shutil.make_archive(targz_file, "gztar", parent_dir, base_dir)

                error_message += "(OK) " + dir + " (" + get_file_size(targz_file + ".tar.gz") + ")\n"
            else:
                error_code = 1
                error_message += "(ERROR) " + dir + " does not exist\n"
        except OSError as e:
            error_code = 2
            error_message += "(ERROR) " + dir + " (" + get_file_size(targz_file + ".tar.gz") + ") " \
                             + e.strerror + "\n"
        except subprocess.CalledProcessError as e:
            error_code = 1
            error_message += "(ERROR) " + dir + " (" + get_file_size(targz_file + ".tar.gz") + ") " \
                             + e.output.rstrip("\n") + "\n"

    return error_code, error_message


def export_db(alias, host, port, database, user, password, exclude, target_dir, command_path):
    """ Export database using the current configuration.

    Keyword arguments:
    alias -- Name for the dumped file.
    host -- Host to connect to the database.
    port -- Port to connect to the database.
    database -- Name of the database.
    user -- User to connect to the database.
    password -- Password to connect to the database.
    exclude -- String with tables to be excluded with comma separated.
    target_dir -- Directory where the dumped files will be created.
    command_path -- Path of the command to be executed.

    Returns: An error code and error message.
    """
    error_code = 0
    error_message = ""

    try:
        target_file = os.path.join(target_dir, alias + ".sql")

        process_args = [command_path, "-u", user, "--port", port, "-p" + password, "-h", host, database,
                        "--force", "--single-transaction", "--result-file", target_file]
        for table in exclude.replace(' ', '').split(','):
            process_args.extend(["--ignore-table", database + "." + table])

        process_output = subprocess.check_output(process_args, stderr=subprocess.STDOUT, universal_newlines=True)
        error_message += "(OK) " + alias + ".sql" + " (" + get_file_size(target_file) + ")\n"
    except subprocess.CalledProcessError as e:
        error_code = 1
        error_message += "(ERROR) " + alias + ".sql" + " (" + get_file_size(target_file) + ") " + e.output.rstrip("\n") + "\n"

    return error_code, error_message


def check_size_db(alias, host, port, database, user, password, max_size, command_path):
    """ Checks if the size of a database has reached some maximum size.

    Keyword arguments:
    alias -- Name for the dumped file.
    host -- Host to connect to the database.
    port -- Port to connect to the database.
    database -- Name of the database.
    user -- User to connect to the database.
    password -- Password to connect to the database.
    max_size -- Limit that must be not limit_reached in MB.
    command_path -- Path of the command to be executed.

    Returns: A tuple containing a boolean and a error message.
    The boolean limit_reached will be True if the current size of the database
    checked is greater than the max_size.
    """
    error_code = 0
    error_message = ""
    db_size = 0

    try:
        query = '''SELECT table_schema AS "Database", SUM(data_length + index_length)/1024/1024 AS "Size in MB"
        FROM information_schema.TABLES
        WHERE table_schema='{database}'
        GROUP BY table_schema;'''.format(database=database)

        process_args = [command_path, "-u", user, "-p" + password, "-h", host, "--port", port, "-e", query]
        process_output = subprocess.check_output(process_args, stderr=subprocess.STDOUT, universal_newlines=True)

        # Strip the content of the string to get the numeric value and discard the rest
        for line in process_output.splitlines():
            if line.rsplit('\t')[0] == database:
                db_size = float(line.rsplit('\t')[1])

        if db_size > int(max_size):
            error_code = 1
            error_message += "(WARNING) " + alias + " (" + convert_size(db_size) + ")" + "\n"
        else:
            error_message += "(OK) " + alias + " (" + convert_size(db_size) + ")" + "\n"
    except subprocess.CalledProcessError as e:
        error_code = 2
        error_message += "(ERROR) " + alias + " " + e.output.rstrip("\n") + "\n"

    return error_code, error_message


def delete_dirs_remote(dir_remote, days, command_path):
    """ Deletes directories that are older than X days in remote directory.

    Keyword arguments:
    dir_remote -- Remote directory.
    days -- Min days to keep directory.
    command_path -- Path to the executable.

    Returns: An error code and error message.
    """
    error_code = 0
    error_message = ""
    dir_name = ''

    try:
        process_args_lsd = [command_path, "lsd", dir_remote]
        process_output_lsd = subprocess.check_output(process_args_lsd, stderr=subprocess.STDOUT,
                                                     universal_newlines=True)
        lines = process_output_lsd.splitlines()[1:]
        for line in lines:
            dir_name = line.split()[4]
            dir_date = datetime.datetime.strptime(line.split()[1], '%Y-%m-%d')
            dir_date_diff = (datetime.datetime.now().date() - dir_date.date()).days
            if dir_date_diff > days:
                process_args_purge = [command_path, "purge", dir_remote + "/" + dir_name]
                process_output_purge = subprocess.check_output(process_args_purge, stderr=subprocess.STDOUT,
                                                               universal_newlines=True)
                error_message += "(OK) " + dir_remote + "/" + dir_name + "\n"
    except subprocess.CalledProcessError as e:
        error_code = 1
        error_message += "(ERROR) " + dir_remote + "/" + dir_name + "\n" + e.output.rstrip("\n") + "\n"

    return error_code, error_message


def upload_dir(path_local, path_remote, upload_low_memory, upload_log, command_path):
    """ Uploads a directory to remote directory.

    Keyword arguments:
    path_local -- Local directory to upload.
    path_remote -- Remote directory where upload.
    upload_low_memory -- Force to use low memory to upload.
    upload_log -- Log progress upload process.
    command_path -- Path to the executable.

    Returns: An error message
    """
    error_code = 0
    error_message = ""

    process_args = [command_path, "copy", path_local, path_remote]
    if upload_log:
        process_args.extend(["-v", "--stats-one-line"])
    if upload_low_memory:
        process_args.extend(["--checkers", "1", "--transfers", "1", "--use-mmap", "--buffer-size", "0M", "--tpslimit",
                                   "1", "--no-traverse", "--cache-chunk-no-memory"])

    try:
        process_output = subprocess.check_output(process_args, stderr=subprocess.STDOUT, universal_newlines=True)
        error_message += "(OK) " + path_local + " (" + get_dir_size(path_local) + ")" + "\n" + str(process_output)
    except subprocess.CalledProcessError as e:
        error_code = 1
        error_message += "(ERROR) " + path_local + "\n" + e.output.rstrip("\n") + "\n"

    return error_code, error_message


def send_mail_smtp(subject, send_from, send_to, body, smtp_server, port, user, password, files=None, TLS=True):
    """ Sends an email by SMTP protocol with the specified data

    Keyword arguments:
    subject -- Subject of the message.
    send_from -- Sender of the message.
    send_to -- Receiver of the message.
    body --Body of the message (it can contains HTML tags).
    smtp_server -- URL of the SMTP server.
    port -- Port of the smtp server.
    user -- Email of the sender for authentication.
    password -- Password of the sender for authentication
    files -- List of files to be attached (optional)
    TLS -- Decide if use TLS or SSL as encryption mechanism (default to True)

    Returns: An error message.
    """
    error_message = ""
    timeout = False

    # Create the message
    msg = email.message.EmailMessage()
    msg['Subject'] = subject
    msg['From'] = send_from
    msg['To'] = send_to

    # Set the type to HTML
    msg.add_header('Content-Type', 'text/html')
    msg.set_payload(body)

    # Attach files
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

    # Create the connection (TLS or SSL)
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

    # If the limit time hasn't passed
    if not timeout:
        smtpObj.ehlo()
        if TLS:
            smtpObj.starttls()

        # Login to authenticate with the mail server
        try:
            smtpObj.login(user, password)
        except smtplib.SMTPAuthenticationError:
            error_message += "Error de autentificación. Comprueba usuario y contraseña." + "\n"

        # Send the mail
        try:
            smtpObj.sendmail(msg['From'], [msg['To']], msg.as_string().encode('utf-8'))
        except smtplib.SMTPSenderRefused:
            error_message += "El servidor de correo rechazó la conexión." + "\n"
        # Close the connection
        smtpObj.quit()

    return error_message


def send_mail_sendmail(subject, send_from, send_to, body, command_path):
    """ Sends an email by sendmail with the specified data

    Keyword arguments:
    subject -- Subject of the message.
    send_from -- Sender of the message.
    send_to -- Receiver of the message.
    body -- Body of the message (it can contains HTML tags).

    Returns: An error message.
    """
    error_message = ""

    msg = MIMEMultipart('alternative')
    msg["From"] = send_from
    msg["To"] = send_to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, 'html', 'UTF-8'))

    process_output = Popen([command_path, "-t", "-oi"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE,
                           universal_newlines=True)
    stdout, stderr = process_output.communicate(msg.as_string())
    if process_output != 0:
        error_message = stderr

    return error_message


def time_ago(days):
    ''' Calculate the date of N days ago and format the result.

    Keyword arguments:
    days -- How many days ago

    Returns: The calculated date with a proper format
    '''
    date_N_days_ago = datetime.datetime.now() - datetime.timedelta(days=days)

    return date_N_days_ago.strftime("%Y-%m-%dT00:00:00")


def get_file_size(file):
    """ Size and unit from file.

    Keyword arguments:
    file -- File path.

    Returns: Size and unit.
    """
    return convert_size(os.path.getsize(file) / 1024 / 1024)

def get_dir_size(path):
    """ Size and unit from path.

    Keyword arguments:
    path -- Directory path.

    Returns: Size and unit.
    """
    size = 0
    with os.scandir(path) as items:
        for item in items:
            if item.is_file():
                size += item.stat().st_size
            elif item.is_dir():
                size += get_dir_size(item.path)

    return convert_size(size / 1024 / 1024)

def convert_size(size_mb):
    """ Convert MB size to GB size if it is necessary.

    Keyword arguments:
    size -- Size in MB.

    Returns: Size and unit.
    """
    if size_mb > 1024:
        return str(round(size_mb / 1024)) + "GB"
    else:
        return str(round(size_mb)) + "MB"


def output_format(element, message=''):
    """ Change message to HTML format.

    Keyword arguments:
    element -- HTML element.
    message -- String to format.

    Returns: String with HTML format
    """
    if element == 'table-open':
        return '<table style="font-family: Helvetica; font-size: 1.1em; line-height: 1.4; \
                border-collapse: collapse; width: 100%; background-color: #fff;">'
    elif element == 'table-close':
        return '</table>'
    elif element == 'caption':
        return '<caption style="font-size: 1.2em; font-weight: bold; font-variant: small-caps; padding: 5px;">' + message + '</caption>'
    elif element == 'row-header':
        return '<tr style="color: #fff; text-transform: uppercase; background-color: #36304a;"> \
                <td style="padding: 10px;">' + message + '</td></tr>'
    elif element == 'row-action':
        return '<tr style="color: gray; background-color: #f2f2f2;"><td style="padding: 10px;">' + message + \
               '</td></tr>'
    elif element == 'row':
        return '<tr style="color: #2b2b2b;"><td style="padding: 5px 10px">' + message + '</td></tr>'
    elif element == 'version':
        return '<p style="color: gray; font-size: 0.8em;">' + __repository__ + ' [version: ' + __version__ + ']</p>'


# Main Script
if __name__ == "__main__":
    # Success of script
    success = True

    # Error code and message
    error_code = 0
    error_message = ""

    # Load and read the configuration file
    if len(sys.argv) == 1:
        sys.exit("El archivo de configuración no se ha especificado")
    if not os.path.exists(sys.argv[1]):
        sys.exit("El archivo de configuración no existe")
    config = configparser.ConfigParser(allow_no_value=True)
    config.optionxform = str
    config.read(sys.argv[1], encoding='utf8')

    # Check local directory
    if config.has_option('general', 'dir_local'):
        dir_local = config['general'].get('dir_local')
        if not os.path.exists(dir_local):
            sys.exit("El directorio de copias local no existe")
    else:
        sys.exit("El directorio de copias local no se ha especificado (dir_local)")

    # Create log file
    logfile = os.path.join(dir_local, os.path.basename(sys.argv[1]) + ".log")
    if os.path.exists(logfile):
        os.remove(logfile)
    log = open(logfile, 'a', encoding='utf8')

    # Start backup
    log.write(output_format('table-open'))
    log.write(output_format('caption', "Registro de actividad"))
    now = datetime.datetime.now()
    log.write(output_format('row-header', "Inicio: " + now.strftime("%d-%m-%Y %H:%M:%S")))

    # Delete local backups
    if config['actions'].getboolean('delete_local'):
        now = datetime.datetime.now()
        log.write(output_format('row-action', "Eliminando copias antiguas locales: " + now.strftime("%H:%M:%S")))
        if config.has_option('general', 'days_keep_local'):
            days_keep = config['general'].getint('days_keep_local')
        else:
            sys.exit("Los días a mantener las copias locales antiguas no se ha especificado (days_keep_local)")
        error_code, error_message = delete_dirs_local(dir_local, days_keep)
        if error_code != 0:
            success = False
        log.write(output_format('row', error_message))

    # Delete remote backups
    if config['actions'].getboolean('delete_remote'):
        now = datetime.datetime.now()
        log.write(output_format('row-action', "Eliminando copias antiguas remotas: " + now.strftime("%H:%M:%S")))
        if config.has_option('general', 'days_keep_remote'):
            days_keep = config['general'].getint('days_keep_remote')
        else:
            sys.exit("Los días a mantener las copias remotas antiguas no se ha especificado (days_keep_remote)")
        if config.has_option('general', 'dir_remote'):
            dir_remote = config['general'].get('dir_remote')
        else:
            sys.exit("El directorio remoto no se ha especificado (dir_remote)")
        if config.has_option('executables', 'rclone'):
            command_path = config['executables'].get('rclone')
            if not os.path.exists(command_path):
                sys.exit("El ejecutable de rclone no existe")
        else:
            sys.exit("El ejecutable de rclone no se ha especificado (rclone)")
        error_code, error_message = delete_dirs_remote(dir_remote, days_keep, command_path)
        if error_code != 0:
            success = False
        log.write(output_format('row', error_message))

    # Create current backup directory in local directory
    dir_current_backup_path = None
    dir_current_backup_name = None
    if config['actions'].getboolean('compress_dir') or config['actions'].getboolean('export_db'):
        now = datetime.datetime.now()
        dir_current_backup_name = now.strftime("%Y%m%d-%H%M%S")
        dir_current_backup_path = os.path.join(dir_local, dir_current_backup_name)
        os.makedirs(dir_current_backup_path)

    # Compress directories
    if config['actions'].getboolean('compress_dir'):
        now = datetime.datetime.now()
        log.write(output_format('row-action', "Comprimiendo directorios a local: " + now.strftime("%H:%M:%S")))
        dirs_compress = config['directories'].items()
        compress_method = config['general'].get('compress_method', fallback='Python')
        command_path = ''
        if compress_method == 'Tar':
            if config.has_option('executables', 'tar'):
                command_path = config['executables'].get('tar')
                if not os.path.exists(command_path):
                    sys.exit("El ejecutable de tar no existe")
            else:
                sys.exit("El ejecutable de tar no se ha especificado (tar)")
        error_code, error_message = compress_dirs_local(dirs_compress, dir_current_backup_path, compress_method, command_path)
        if error_code != 0:
            success = False
        log.write(output_format('row', error_message))

    # Export databases
    if config['actions'].getboolean('export_db'):
        now = datetime.datetime.now()
        log.write(output_format('row-action', "Exportando bases de datos a local: " + now.strftime("%H:%M:%S")))
        for section in config.sections():
            if "database" in section and config[section].getboolean('export'):
                if config.has_option(section, 'alias'):
                    alias = config[section].get('alias')
                else:
                    sys.exit("El alias de la base de datos no se ha especificado (alias)")
                if config.has_option(section, 'host'):
                    host = config[section].get('host')
                else:
                    sys.exit("El host de la base de datos no se ha especificado (host)")
                if config.has_option(section, 'port'):
                    port = config[section].get('port')
                else:
                    sys.exit("El puerto de la base de datos no se ha especificado (port)")
                if config.has_option(section, 'database'):
                    database = config[section].get('database')
                else:
                    sys.exit("El nombre de la base de datos no se ha especificado (database)")
                if config.has_option(section, 'user'):
                    user = config[section].get('user')
                else:
                    sys.exit("El usuario de la base de datos no se ha especificado (user)")
                if config.has_option(section, 'password'):
                    password = config[section].get('password')
                else:
                    sys.exit("La contraseña de la base de datos no se ha especificado (password)")
                exclude = config[section].get('exclude', fallback='')
                """
                excludes = []
                for key in config[section].keys():
                    if "exclude" in key:
                        excludes.append(config[section][key])
                """
                if config.has_option('executables', 'mysqldump'):
                    command_path = config['executables'].get('mysqldump')
                    if not os.path.exists(command_path):
                        sys.exit("El ejecutable de mysqldump no existe")
                else:
                    sys.exit("El ejecutable de mysqldump no se ha especificado (mysqldump)")

                error_code, error_message = export_db(alias, host, port, database, user, password, exclude,
                                                      dir_current_backup_path, command_path)
                if error_code != 0:
                    success = False
                log.write(output_format('row', error_message))

    # Check size databases
    if config['actions'].getboolean('check_db_size'):
        now = datetime.datetime.now()
        log.write(output_format('row-action', "Comprobando tamaño bases de datos: " + now.strftime("%H:%M:%S")))
        for section in config.sections():
            if "database" in section and config[section].getboolean('check_size'):
                if config.has_option(section, 'alias'):
                    alias = config[section].get('alias')
                else:
                    sys.exit("El alias de la base de datos no se ha especificado (alias)")
                if config.has_option(section, 'host'):
                    host = config[section].get('host')
                else:
                    sys.exit("El host de la base de datos no se ha especificado (host)")
                if config.has_option(section, 'port'):
                    port = config[section].get('port')
                else:
                    sys.exit("El puerto de la base de datos no se ha especificado (port)")
                if config.has_option(section, 'database'):
                    database = config[section].get('database')
                else:
                    sys.exit("El nombre de la base de datos no se ha especificado (database)")
                if config.has_option(section, 'user'):
                    user = config[section].get('user')
                else:
                    sys.exit("El usuario de la base de datos no se ha especificado (user)")
                if config.has_option(section, 'password'):
                    password = config[section].get('password')
                else:
                    sys.exit("La contraseña de la base de datos no se ha especificado (password)")
                if config.has_option(section, 'max_size'):
                    max_size = config[section].get('max_size')
                else:
                    sys.exit("La contraseña de la base de datos no se ha especificado (max_size)")
                if config.has_option('executables', 'mysqldump'):
                    command_path = config['executables'].get('mysql')
                    if not os.path.exists(command_path):
                        sys.exit("El ejecutable de mysql no existe")
                else:
                    sys.exit("El ejecutable de mysqldump no se ha especificado (mysql)")

                error_code, error_message = check_size_db(alias, host, port, database, user, password, max_size,
                                                          command_path)
                if error_code != 0:
                    success = False
                log.write(output_format('row', error_message))

    # Upload backup
    if config['actions'].getboolean('upload_dir'):
        if config['actions'].getboolean('compress_dir') or config['actions'].getboolean('export_db'):
            now = datetime.datetime.now()
            log.write(output_format('row-action', "Subiendo copias a remoto: " + now.strftime("%H:%M:%S")))
            if config.has_option('general', 'dir_remote'):
                dir_remote = config['general'].get('dir_remote')
            else:
                sys.exit("El directorio remoto no se ha especificado (dir_remote)")
            if config.has_option('executables', 'rclone'):
                command_path = config['executables'].get('rclone')
                if not os.path.exists(command_path):
                    sys.exit("El ejecutable de rclone no existe")
            else:
                sys.exit("El ejecutable de rclone no se ha especificado (rclone)")
            upload_low_memory = config['general'].getboolean('upload_low_memory', fallback=False)
            upload_log = config['general'].getboolean('upload_log', fallback=False)
            error_code, error_message = upload_dir(dir_current_backup_path, dir_remote + "/" + dir_current_backup_name,
                                                   upload_low_memory, upload_log, command_path)
            if error_code != 0:
                success = False
            log.write(output_format('row', error_message))
        else:
            sys.exit("Has elegido subir la copia pero no exportas directorios ni bases de datos")

    # Close log file
    now = datetime.datetime.now()
    log.write(output_format('row-header', "Fin: " + now.strftime("%d-%m-%Y %H:%M:%S")))
    log.write(output_format('table-close'))
    log.write(output_format('version'))
    log.close()

    # Copy log file in current backup directory
    if config['actions'].getboolean('compress_dir') or config['actions'].getboolean('export_db'):
        shutil.copy(logfile, dir_current_backup_path)

    # Send email
    send_email_action = config['actions'].get('send_email', fallback='Never')
    if send_email_action == 'Always' or (send_email_action == 'OnlyError' and not success):
        subject = config['email'].get('subject', fallback='HostingBackup Log')
        if success:
            subject += " (OK)"
        else:
            subject += " (ERROR)"

        log = open(logfile, 'r', encoding='utf8')
        body = log.read()
        log.close()

        body = body.replace("\n", "<br />")

        if config.has_option('email', 'sender'):
            sender = config['email'].get('sender')
        else:
            sys.exit("El remitente del email no se ha especificado (sender)")
        if config.has_option('email', 'receiver'):
            receiver = config['email'].get('receiver')
        else:
            sys.exit("El destinatario del email no se ha especificado (receiver)")

        if config['email']['method'] == 'smtp':
            if config.has_option('email', 'smtp_server'):
                smtp_server = config['email'].get('smtp_server')
            else:
                sys.exit("El servidor SMTP no se ha especificado (smtp_server)")
            if config.has_option('email', 'smtp_port'):
                smtp_port = config['email'].get('smtp_port')
            else:
                sys.exit("El puerto del servidor SMTP no se ha especificado (smtp_port)")
            if config.has_option('email', 'smtp_user'):
                smtp_user = config['email'].get('smtp_user')
            else:
                sys.exit("El usuario del servidor SMTP no se ha especificado (smtp_user)")
            if config.has_option('email', 'smtp_password'):
                smtp_password = config['email'].get('smtp_password')
            else:
                sys.exit("El puerto del servidor SMTP no se ha especificado (smtp_password)")
            TLS = config['email'].getboolean('TLS')
            error_send_mail = send_mail_smtp(subject, sender, receiver, body, smtp_server, smtp_port,
                                             smtp_user, smtp_password, files=None, TLS=True)
        elif config['email']['method'] == 'sendmail':
            if config.has_option('executables', 'sendmail'):
                command_path = config['executables'].get('sendmail')
                if not os.path.exists(command_path):
                    sys.exit("El ejecutable de sendmail no existe")
            else:
                sys.exit("El ejecutable de sendmail no se ha especificado (sendmail)")
            error_send_mail = send_mail_sendmail(subject, sender, receiver, body, command_path)

        sys.exit(error_send_mail)

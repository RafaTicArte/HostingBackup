# HostingBackup

HostingBackup es un script desarrollado en Python para automatizar la copia de seguridad en un servidor web o similar. Se ideó para ser utilizado en un hosting compartido con acceso SSH en el que no se tienen privilegios para instalar software adicional.

## Funcionalidades

El script en cada ejecución crea un nuevo directorio con el contenido de la copia de seguridad.

- Compresión de directorios.
- Exportación de bases de datos MySQL/MariaDB.
- Chequeo del tamaño de bases de datos MySQL/MariaDB.
- Subida de copias de seguridad a un servicio remoto.
- Eliminación de copias de seguridad antiguas tanto en local como en servicio remoto.
- Envío de correos electrónicos con el registro de acciones de la copia de seguridad.

## Requisitos

- Sistema operativo Linux.
- [Python 3.5+](https://www.python.org/).
- [Rclone](https://rclone.org/).
- Sendmail.

## Descarga

[https://github.com/RafaTicArte/HostingBackup/releases](https://github.com/RafaTicArte/HostingBackup/releases)

## Instalación

Descomprimir, configurar y usar.

## Configuración

Crea un fichero de configuración INI con las acciones que desees llevar a cabo en la copia de seguridad.

En el archivo de configuración descargado están explicados todos los parámetros posibles.

## Uso

Uso general:

```shell
python hostingbackup.py configuration.ini
```

Para redirigir la salida de errores a un fichero, ya que lo normal es ejecutar el script en segundo plano desde una tarea programada:

```shell
python hostingbackup.py configuration.ini &>> hostingbackup-db.log
```

Rclone puede llegar a consumir mucha memoria. Para reducir el consumo podemos realizar las siguientes acciones:
- Establecer la variable de entorno de GO `export GOGC=20` para que el recolector de basura use menos memoria ([más información](https://rclone.org/faq/#rclone-is-using-too-much-memory-or-appears-to-have-a-memory-leak)).
- Establecer el uso de memoria del usuario en el sistema `ulimit -u 80`.
- Establecer el parámetro de configuración `upload_low_memory = True`.

```shell
export GOGC=20
ulimit -u 80
python hostingbackup.py configuration.ini
```

## Código fuente

El código fuente está disponible en el repositorio:

[https://github.com/RafaTicArte/HostingBackup](https://github.com/RafaTicArte/HostingBackup)

## Contribución

Pull requests son bienvenidos. Para cambios importantes, abre una discusión con lo que te gustaría cambiar.

## Autores

[Rafa Morales](https://github.com/RafaTicArte)

[Jesús Budia](https://github.com/jesusjbr)


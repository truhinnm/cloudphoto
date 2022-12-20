import os
import pathlib
import sys
import urllib.request

import boto3
import click

index_html_template_start = """<!doctype html>
<html>
    <head>
        <title>Фотоархив</title>
    </head>
<body>
    <h1>Фотоархив</h1>
    <ul>\n
"""

index_html_template_end = """</ul>
</body>"""

album_page_html_template_start = """<!doctype html>
<html>
    <head>
        <link rel="stylesheet" type="text/css" href="https://cdnjs.cloudflare.com/ajax/libs/galleria/1.6.1/themes/classic/galleria.classic.min.css" />
        <style>
            .galleria{ width: 960px; height: 540px; background: #000 }
        </style>
        <script src="https://ajax.googleapis.com/ajax/libs/jquery/3.6.0/jquery.min.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/galleria/1.6.1/galleria.min.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/galleria/1.6.1/themes/classic/galleria.classic.min.js"></script>
    </head>
    <body>
        <div class="galleria">\n"""

album_page_html_template_end = """        </div>
        <p>Вернуться на <a href="index.html">главную страницу</a> фотоархива</p>
        <script>
            (function() {
                Galleria.run('.galleria');
            }());
        </script>
    </body>
</html>"""

error_html_template = """<!doctype html>
<html>
    <head>
        <title>Фотоархив</title>
    </head>
<body>
    <h1>Ошибка</h1>
    <p>Ошибка при доступе к фотоархиву. Вернитесь на <a href="index.html">главную страницу</a> фотоархива.</p>
</body>
</html>"""

CONFIG_FILE_PATH = os.path.expanduser('~/.config/cloudphoto/cloudphotorc')


@click.group()
def commands():
    pass


def connect():
    params = {}
    if not os.path.exists(CONFIG_FILE_PATH):
        click.echo('Error: configuration file is missing', err=True)
        sys.exit(1)
    config_file = open(CONFIG_FILE_PATH)
    for line in config_file:
        key, value = line.partition('=')[::2]
        params[key.strip()] = value.strip()

    required_params = ['bucket', 'aws_access_key_id', 'aws_secret_access_key', 'region', 'endpoint_url']
    for required_param in required_params:
        value = params.get(required_param)
        if not (value and value.strip()):
            click.echo('Error: not all parameters are defined in configuration file', err=True)
            sys.exit(1)

    session = boto3.session.Session()
    s3 = session.client(
        service_name='s3',
        region_name=params['region'],
        endpoint_url=params['endpoint_url'],
        aws_access_key_id=params['aws_access_key_id'],
        aws_secret_access_key=params['aws_secret_access_key']
    )
    bucket_name = params['bucket']
    return s3, bucket_name


@click.command()
def init():
    aws_access_key_id = click.prompt('Enter aws_access_key_id')
    aws_secret_access_key = click.prompt('Enter aws_secret_access_key')
    bucket = click.prompt('Enter bucket name')

    dir_name = os.path.dirname(CONFIG_FILE_PATH)
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)
    config_file = open(CONFIG_FILE_PATH, 'w+')
    config_file.write(f'''[DEFAULT]
bucket = {bucket}
aws_access_key_id = {aws_access_key_id}
aws_secret_access_key = {aws_secret_access_key} 
region = ru-central1 
endpoint_url = https://storage.yandexcloud.net''')
    config_file.close()
    click.echo('Configuration saved')

    s3, bucket_name = connect()
    try:
        s3.head_bucket(Bucket=bucket_name)
    except:
        s3.create_bucket(Bucket=bucket_name)
        click.echo(f'Created new bucket {bucket_name}')


@click.command
@click.option('--album', required=True)
@click.option('--path', type=click.Path(exists=True))
def upload(album, path):
    s3, bucket_name = connect()
    if path is None:
        path = os.getcwd()
    for file in os.listdir(path):
        if file.endswith('.jpg') or file.endswith('.jpeg'):
            try:
                s3.upload_file(f'{path}/{file}', bucket_name, f'{album}/{file}')
            except:
                click.echo(f'Error uploading file {file}', err=True)


@click.command
@click.option('--album', required=True)
@click.option('--path', type=click.Path())
def download(album, path):
    s3, bucket_name = connect()
    prefix = f'{album}/'
    if path is None:
        path = os.getcwd()
    try:
        pathlib.Path(path).mkdir(parents=True, exist_ok=True)
    except:
        click.echo("The specified directory is not available", err=True)
    response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix, Delimiter='/')
    for obj in response['Contents']:
        key = obj['Key']
        if not (key.endswith('.jpg') or key.endswith('.jpeg')):
            continue
        name = key[len(prefix):]
        s3.download_file(bucket_name, key, f'{path}/{name}')
    click.echo("Album downloaded successfully")


@click.command
@click.option('--album')
def list(album):
    s3, bucket_name = connect()
    if album is None:
        response = s3.list_objects_v2(Bucket=bucket_name, Delimiter='/')
        if response['CommonPrefixes'] is None:
            click.echo("Error: there are no albums", err=True)
            sys.exit(1)
        for prefix in response['CommonPrefixes']:
            click.echo(prefix['Prefix'][:-1])
    else:
        prefix = f'{album}/'
        response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix, Delimiter='/')
        if response['KeyCount'] == 0:
            click.echo("Error: the album is empty or it doesn't exist", err=True)
            sys.exit(1)
        for obj in response['Contents']:
            click.echo(obj['Key'][len(prefix):])


@click.command
@click.option('--album', required=True)
@click.option('--photo')
def delete(album, photo):
    s3, bucket_name = connect()
    prefix = f'{album}/'
    if photo is None:
        response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix, Delimiter='/')
        if response['KeyCount'] == 0:
            click.echo("Error: the album is empty or it doesn't exist", err=True)
            sys.exit(1)
        try:
            for obj in response['Contents']:
                s3.delete_object(Bucket=bucket_name, Key=obj['Key'])
        except:
            click.echo("Error: failed to delete album", err=True)
            sys.exit(1)
        click.echo("Album deleted successfully")
    else:
        key = f'{prefix}{photo}'
        try:
            s3.head_object(Bucket=bucket_name, Key=key)
        except:
            click.echo("Error: the photo doesn't exist", err=True)
            sys.exit(1)
        try:
            s3.delete_object(Bucket=bucket_name, Key=key)
            click.echo("Photo deleted successfully")
        except:
            click.echo("Error: failed to delete photo", err=True)
            sys.exit(1)


@click.command
def mksite():
    s3, bucket_name = connect()
    s3.put_bucket_acl(ACL='public-read', Bucket=bucket_name)

    response = s3.list_objects_v2(Bucket=bucket_name, Delimiter='/')
    if response['CommonPrefixes'] is None:
        click.echo("Error: there are no albums", err=True)
        sys.exit(1)

    links_to_albums_html = ''
    i = 1
    for common_prefix in response['CommonPrefixes']:
        prefix = common_prefix['Prefix']
        album = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix, Delimiter='/')
        links_to_photos_html = ''
        for obj in album['Contents']:
            key = obj['Key']
            if not (key.endswith('.jpg') or key.endswith('.jpeg')):
                continue
            url_bucket = urllib.request.pathname2url(bucket_name)
            url_key = urllib.request.pathname2url(key)
            links_to_photos_html += f'<img src=https://storage.yandexcloud.net/{url_bucket}/{url_key} data-title="{key[len(prefix):]}">\n'
        album_page = album_page_html_template_start + links_to_photos_html + album_page_html_template_end
        s3.put_object(Body=album_page, Bucket=bucket_name, Key=f'album{i}.html')
        links_to_albums_html += f'<li><a href="album{i}.html">{prefix[:-1]}</a></li>\n'
        i += 1
    index_page = index_html_template_start + links_to_albums_html + index_html_template_end
    s3.put_object(Body=index_page, Bucket=bucket_name, Key='index.html')
    s3.put_object(Body=error_html_template, Bucket=bucket_name, Key='error.html')

    website_configuration = {
        'ErrorDocument': {'Key': 'error.html'},
        'IndexDocument': {'Suffix': 'index.html'},
    }
    s3.put_bucket_website(Bucket=bucket_name, WebsiteConfiguration=website_configuration)
    click.echo(f'https://{bucket_name}.website.yandexcloud.net')


commands.add_command(init)
commands.add_command(upload)
commands.add_command(download)
commands.add_command(list)
commands.add_command(delete)
commands.add_command(mksite)

if __name__ == '__main__':
    commands()
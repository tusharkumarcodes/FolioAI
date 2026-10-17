project('folio-ai',
  version: '0.1.0',
  meson_version: '>= 0.59.0',
  default_options: ['warning_level=2']
)

gnome = import('gnome')
python = import('python')
py_installation = python.find_installation('python3')

prefix = get_option('prefix')
bindir = prefix / get_option('bindir')
datadir = prefix / get_option('datadir')
pkgdatadir = datadir / meson.project_name()

app_id = 'io.github.tusharkumarcodes.FolioAI'

subdir('data')
subdir('src')

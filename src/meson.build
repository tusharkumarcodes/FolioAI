conf = configuration_data()
conf.set('DATA_DIR', pkgdatadir)
conf.set('PYTHON', py_installation.full_path())

configure_file(
  input: 'folio-ai.in',
  output: 'folio-ai',
  configuration: conf,
  install: true,
  install_dir: bindir,
  install_mode: 'rwxr-xr-x'
)

sources = [
  'folio_ai/__init__.py',
  'folio_ai/main.py',
]

py_installation.install_sources(
  sources,
  subdir: 'folio_ai'
)

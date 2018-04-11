from distutils.spawn import find_executable
import os.path as osp
from setuptools.command.develop import develop as DevelopCommand
from setuptools.command.install import install as InstallCommand
from setuptools import find_packages
from setuptools import setup
import shlex
import subprocess
import sys


PY3 = sys.version_info[0] == 3
PY2 = sys.version_info[0] == 2
assert PY3 or PY2


version = '2.10.5'


install_requires = [
    'matplotlib',
    'numpy',
    'Pillow>=2.8.0',
    'PyYAML',
]


try:
    import PyQt5  # NOQA
    PYQT_VERSION = 5
except ImportError:
    try:
        import PyQt4  # NOQA
        PYQT_VERSION = 4
    except ImportError:
        if PY2:
            sys.stderr.write(
                'Please install PyQt4 or PyQt5 for Python2.\n'
                'Note that PyQt5 can be installed via pip for Python3.')
            sys.exit(1)
        assert PY3
        # PyQt5 can be installed via pip for Python3
        install_requires.append('pyqt5')
        PYQT_VERSION = 5


if sys.argv[1] == 'release':
    commands = [
        'git tag v{:s}'.format(version),
        'git push origin master --tag',
        'python setup.py sdist',
        'twine upload dist/labelme-{:s}.tar.gz'.format(version),
    ]
    sys.exit(sum(subprocess.call(shlex.split(cmd)) for cmd in commands))


here = osp.dirname(osp.abspath(__file__))


def customize(command_subclass):
    orig_run = command_subclass.run

    def customized_run(self):
        pyrcc = 'pyrcc{:d}'.format(PYQT_VERSION)
        if find_executable(pyrcc) is None:
            sys.stderr.write('Please install {:s} command.\n'.format(pyrcc))
            sys.stderr.write('(See https://github.com/wkentaro/labelme.git)\n')
            sys.exit(1)
        package_dir = osp.join(here, 'labelme')
        src = 'resources.qrc'
        dst = 'resources.py'
        cmd = '{pyrcc} -o {dst} {src}'.format(pyrcc=pyrcc, src=src, dst=dst)
        print('+ {:s}'.format(cmd))
        subprocess.call(shlex.split(cmd), cwd=package_dir)
        orig_run(self)

    command_subclass.run = customized_run
    return command_subclass


@customize
class CustomDevelopCommand(DevelopCommand):
    pass


@customize
class CustomInstallCommand(InstallCommand):
    pass


setup(
    name='labelme',
    version=version,
    packages=find_packages(),
    cmdclass={
        'develop': CustomDevelopCommand,
        'install': CustomInstallCommand,
    },
    description='Image Polygonal Annotation with Python.',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='Kentaro Wada',
    author_email='www.kentaro.wada@gmail.com',
    url='https://github.com/wkentaro/labelme',
    install_requires=install_requires,
    license='GPLv3',
    keywords='Image Annotation, Machine Learning',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX',
        'Topic :: Internet :: WWW/HTTP',
    ],
    package_data={'labelme': ['icons/*', 'resources.qrc']},
    entry_points={
        'console_scripts': [
            'labelme=labelme.app:main',
            'labelme_draw_json=labelme.cli.draw_json:main',
            'labelme_json_to_dataset=labelme.cli.json_to_dataset:main',
            'labelme_on_docker=labelme.cli.on_docker:main',
        ],
    },
)

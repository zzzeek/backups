from setuptools import setup


setup(name='backups',
      version=1.0,
      description="Front end for duplicity",
      classifiers=[
      'Development Status :: 4 - Beta',
      'Environment :: Console',
      'Programming Language :: Python',
      'Programming Language :: Python :: 3',
      'Programming Language :: Python :: Implementation :: CPython',
      'Programming Language :: Python :: Implementation :: PyPy',
      ],
      author='Mike Bayer',
      author_email='mike@zzzcomputing.com',
      url='http://bitbucket.org/zzzeek/backups',
      license='MIT',
      packages=["backups"],
      zip_safe=False,
      entry_points={
        'console_scripts': ['backups = backups.backups:main',
                    'synthetic = backups.synthetic:main'],
      }
)

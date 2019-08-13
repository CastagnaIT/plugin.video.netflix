Contributing Guidelines
=======================

We love getting feedback from our users. Bugs and code contributions are great forms of feedback and we thank you for any bugs you report or code you contribute.

Reporting Issues
----------------

Before reporting a new bug, please `check first <https://bugs.mysql.com/search.php>`_ to see if a similar bug already exists.

Bug reports should be as complete as possible. Please try and include the following:

- Complete steps to reproduce the issue.
- Any information about platform and environment that could be specific to the bug.
- Specific version of the product you are using.
- Specific version of the server being used.
- Sample code to help reproduce the issue if possible.

Contributing Code
-----------------

Contributing to this project is easy. You just need to follow these steps.

- Make sure you have a user account at `bugs.mysql.com <https://bugs.mysql.com>`_. You will need to reference this user account when you submit your Oracle Contributor Agreement (OCA).
- Sign the Oracle Contributor Agreement. You can find instructions for doing that at the `OCA Page <https://www.oracle.com/technetwork/community/oca-486395.html>`_.
- Develop your pull request. Make sure you are aware of the `requirements <https://dev.mysql.com/doc/dev/connector-python/8.0/requirements.html>`_ for the project.
- Validate your pull request by including tests that sufficiently cover the functionality you are adding.
- Verify that the entire test suite passes with your code applied.
- Submit your pull request. While you can submit the pull request via `GitHub <https://github.com/mysql/mysql-connector-python/pulls>`_, you can also submit it directly via `bugs.mysql.com <https://bugs.mysql.com>`_.

Thanks again for your wish to contribute to MySQL. We truly believe in the principles of open source development and appreciate any contributions to our projects.

Running Tests
-------------

Any code you contribute needs to pass our test suite. Please follow these steps to run our tests and validate your contributed code.

1) Make sure you have the necessary `prerequisites <https://dev.mysql.com/doc/dev/connector-python/8.0/installation.html#prerequisites>`_ for building the project and `Pylint <https://www.pylint.org/>`_ for code analysis and style

2) Clone MySQL Connector/Python

   .. code-block:: bash

       shell> git clone https://github.com/mysql/mysql-connector-python.git

3) Run the entire test suite

   .. code-block:: bash

       shell> python unittests.py --with-mysql=<mysql-dir> --with-mysql-capi=<mysql-capi-dir> --with-protobuf-include-dir=<protobuf-include-dir> --with-protobuf-lib-dir=<protobuf-lib-dir> --with-protoc=<protoc-binary> --extra-link-args="-L<mysql-lib-dir> -lssl -lcrypto"

   Example:

   .. code-block:: sh

       shell> python unittests.py --with-mysql=/usr/local/mysql --with-mysql-capi=/usr/local/mysql --with-protobuf-include-dir=/usr/local/protobuf/include --with-protobuf-lib-dir=/usr/local/protobuf/lib --with-protoc=/usr/local/protobuf/bin/protoc --extra-link-args="-L/usr/local/mysql/lib -lssl -lcrypto"


Getting Help
------------

If you need help or just want to get in touch with us, please use the following resources:

- `MySQL Connector/Python Developer Guide <https://dev.mysql.com/doc/connector-python/en/>`_
- `MySQL Connector/Python X DevAPI Reference <https://dev.mysql.com/doc/dev/connector-python/>`_
- `MySQL Connector/Python Forum <http://forums.mysql.com/list.php?50>`_
- `MySQL Public Bug Tracker <https://bugs.mysql.com>`_
- `Slack <https://mysqlcommunity.slack.com>`_ (`Sign-up <https://lefred.be/mysql-community-on-slack/>`_ required if you do not have an Oracle account)
- `Stack Overflow <https://stackoverflow.com/questions/tagged/mysql-connector-python>`_
- `InsideMySQL.com Connectors Blog <https://insidemysql.com/category/mysql-development/connectors/>`_


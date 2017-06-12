pymaestro
=========

A work in progress Python port of the Pololu Maestro USB SDK with a fully functional bytecode compiler.

Features
--------

pymaestro can be used as a drop in replacement for the Pololu Meastro USB SDK. THe only major caveat is that driver support is limited to those that are supported by PyUSB. On Windows, the native Pololu Maestro driver is not compatible with PyUSB. The native driver needs to be replaced with libusb-win32 (although others might work as well). This can be done easily with software such as zadig_.

Most features of the Usc class are implemented. Saving configuration files to xml is currently not supported, although it is planned in the next release. 

.. _zadig: http://zadig.akeo.ie

Usage
-----


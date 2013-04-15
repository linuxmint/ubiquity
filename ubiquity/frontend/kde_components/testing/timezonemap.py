# -*- coding: utf-8 -*-

import sys

from PyQt4 import QtGui, uic
from ubiquity.frontend.kde_components.Timezone import TimezoneMap


if __name__ == "__main__":
    app = QtGui.QApplication(sys.argv)
    QtGui.QApplication.setStyle("Oxygen")
    qss = open("/usr/share/ubiquity/qt/style.qss").read()
    app.setStyleSheet(qss)

    page = uic.loadUi('/usr/share/ubiquity/qt/stepLocation.ui')
    tzmap = TimezoneMap(page.map_frame)
    page.map_frame.layout().addWidget(tzmap)
    page.show()

    sys.exit(app.exec_())

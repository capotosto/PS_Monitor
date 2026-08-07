TOP=../..

include $(TOP)/configure/CONFIG

PROD_IOC = psuMonitor

DBD += psuMonitor.dbd

psuMonitor_DBD += base.dbd
psuMonitor_DBD += pscCore.dbd

psuMonitor_SRCS += psuMonitor_registerRecordDeviceDriver.cpp
psuMonitor_SRCS_DEFAULT += psuMonitorMain.cpp

psuMonitor_LIBS += pscCore
psuMonitor_LIBS += $(EPICS_BASE_IOC_LIBS)

psuMonitor_SYS_LIBS += event_core
psuMonitor_SYS_LIBS += event_extra
psuMonitor_SYS_LIBS_Linux += event_pthreads

include $(TOP)/configure/RULES

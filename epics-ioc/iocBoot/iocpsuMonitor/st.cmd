#!../../bin/linux-x86_64/psuMonitor

< envPaths

cd "${TOP}"

dbLoadDatabase("dbd/psuMonitor.dbd")
psuMonitor_registerRecordDeviceDriver(pdbbase)

epicsEnvSet("P",      "TEST:")
epicsEnvSet("R",      "GIGA")
epicsEnvSet("DEVICE", "GIGA_PSC")
epicsEnvSet("HOST",   "192.168.1.177")
epicsEnvSet("PORT",   "8765")

# Final argument enables PSCDriver's receive-inactivity timeout.
createPSC("$(DEVICE)", "$(HOST)", $(PORT), 1)

dbLoadRecords("db/gigaPscBase.db", "P=$(P),R=$(R),DEVICE=$(DEVICE)")
dbLoadTemplate("db/gigaPsc.substitutions", "P=$(P),R=$(R),DEVICE=$(DEVICE)")

cd "${TOP}/iocBoot/${IOC}"
iocInit()

# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
#
# This file is part of Sick Beard.
#
# Sick Beard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sick Beard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.



from sickbeard import common, db, exceptions, helpers, nzb
from sickbeard.logging import *
from sickbeard.common import * 

import datetime
import sqlite3
import threading
import time
import traceback

class CurrentSearchScheduler():

    def __init__(self, runAtStart=True):
        
        self.isActive = False
        if runAtStart:
            self.lastRun = datetime.datetime.fromordinal(1)
        else:
            self.lastRun = datetime.datetime.now()

        self.searcher = CurrentSearcher()
        self.cycleTime = datetime.timedelta(minutes=10)
        
        self.thread = None
        self.initThread()
        
        self.abort = False
    
    def initThread(self):
        if self.thread == None or not self.thread.isAlive():
            self.thread = threading.Thread(None, self.runSearch, "SEARCH")
    
    def runSearch(self):
        
        while True:
            
            currentTime = datetime.datetime.now()
            
            if currentTime - self.lastRun > self.cycleTime:
                self.lastRun = currentTime
                try:
                    self.searcher.searchForTodaysEpisodes()
                except Exception as e:
                    Logger().log("Search generated an exception: " + str(e), ERROR)
                    Logger().log(traceback.format_exc(), DEBUG)
            
            if self.abort:
                self.abort = False
                self.thread = None
                return
            
            time.sleep(1) 
            

class CurrentSearcher():
    
    def __init__(self):
        self.lock = threading.Lock()
        self.cycleTime = datetime.timedelta(minutes=5)
    
    def searchForTodaysEpisodes(self):

        self._changeMissingEpisodes()

        sickbeard.updateMissingList()
        sickbeard.updateAiringList()
        sickbeard.updateComingList()

        with self.lock:
    
            Logger().log("Beginning search for todays episodes", DEBUG)
    
            #epList = self._getEpisodesToSearchFor()
            epList = sickbeard.missingList + sickbeard.airingList
            
            if epList == None or len(epList) == 0:
                Logger().log("No episodes were found to download")
                return
            
            for curEp in epList:
                
                foundNZBs = nzb.findNZB(curEp)
                
                if len(foundNZBs) == 0:
                    Logger().log("Unable to find NZB for " + curEp.prettyName())
                
                else:
                    
                    # just use the first result for now
                    nzb.snatchNZB(foundNZBs[0])



    def _changeMissingEpisodes(self):
        
        myDB = db.DBConnection()
        myDB.checkDB()

        curDate = datetime.date.today().toordinal()

        Logger().log("Changing all old missing episodes to status MISSED")
        
        try:
            sql = "SELECT * FROM tv_episodes WHERE status=" + str(UNAIRED) + " AND airdate < " + str(curDate)
            sqlResults = myDB.connection.execute(sql).fetchall()
        except sqlite3.DatabaseError as e:
            Logger().log("Fatal error executing query '" + sql + "': " + str(e), ERROR)
            raise
    
        for sqlEp in sqlResults:
            
            try:
                show = helpers.findCertainShow (sickbeard.showList, int(sqlEp["showid"]))
            except exceptions.MultipleShowObjectsException:
                Logger().log("ERROR: expected to find a single show matching " + sqlEp["showid"]) 
                return None
            ep = show.getEpisode(sqlEp["season"], sqlEp["episode"], True)
            with ep.lock:
                ep.status = MISSED
                ep.saveToDB()


    def _getEpisodesToSearchFor(self):
    
        myDB = db.DBConnection()
        myDB.checkDB()
        
        curDate = datetime.date.today().toordinal()
        sqlResults = []
        
        foundEps = []
        
        self._changeMissingEpisodes()
        
        Logger().log("Searching the database for a list of new episodes to download")
        
        try:
            sql = "SELECT * FROM tv_episodes WHERE status IN (" + str(UNKNOWN) + ", " + str(UNAIRED) + ", " + str(PREDOWNLOADED) + ", " + str(MISSED) + ") AND airdate <= " + str(curDate)
            Logger().log("SQL: " + sql, DEBUG)
            sqlResults = myDB.connection.execute(sql).fetchall()
        except sqlite3.DatabaseError as e:
            Logger().log("Fatal error executing query '" + sql + "': " + str(e), ERROR)
            raise
    
        for sqlEp in sqlResults:
            print "FFS the status is " + str(sqlEp["status"])
            
            try:
                show = helpers.findCertainShow (sickbeard.showList, int(sqlEp["showid"]))
            except exceptions.MultipleShowObjectsException:
                Logger().log("ERROR: expected to find a single show matching " + sqlEp["showid"]) 
                return None
            ep = show.getEpisode(sqlEp["season"], sqlEp["episode"], True)
            foundEps.append(ep)
            Logger().log("Added " + ep.prettyName() + " to the list of episodes to download (status=" + str(ep.status))
        
        return foundEps

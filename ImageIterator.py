from io import StringIO
from shutil import copy

import numpy as np
import pandas as pd
import requests
import tempfile
import zipfile
import shutil
import netrc
import json
import os
import slicer
from DICOMLib import DICOMUtils


class ImageIterator:
    """
    Object to retrieve and store annotation information
    """
    def __init__(self):
        self._scans = None
        self._current_scan = None
        self._current_scan_folder = None
        self._current_annotation = False
        self._skip_annotated = False
    
    def __enter__(self):
        return self

    def _get_scans(self, filepath=None):
        raise NotImplementedError("Method is abstract")
        
    def store_annotations(self, annotation_file):
        raise NotImplementedError("Method is abstract")

    def get_scan_folder(self):
        raise NotImplementedError("Method is abstract")

    def load_volume(self):
        raise NotImplementedError("Method is abstract")

    def load_annotation(self):
        raise NotImplementedError("Method is abstract")

    def has_annotation(self):
        return self._current_annotation is not None

    def set_skip_annotated(self, bool_value):
        self._skip_annotated = bool_value
    
    def __iter__(self):
        """
        Initialise the iterator to first scan in the data frame
        :return: self
        """
        self._current_scan_index = 0
        return self

    def __next__(self):        
        raise NotImplementedError("Method is abstract")

    def __exit__(self, exc_t, exc_va, exc_bt):
        raise NotImplementedError("Method is abstract")


class LocalFileIterator(ImageIterator):
    """
    Simple object to retrieve and store information locally
    """
    
    def __init__(self, local_file_path):
        super().__init__()
        self._get_scans(local_file_path)
        
    def _get_scans(self, filepath=None):
        # ToDo raise error for empty path, handle csv loading for list of files
        if os.path.isdir(filepath):
            self._scans = [os.path.join(filepath, f) for f in os.listdir(filepath)
                           if f.endswith(".nii.gz")]
        else:
            self._scans = pd.read_csv(filepath)
        
    def store_annotations(self, annotation_file):
        """
        Save annotation file locally, along scan file
        :param annotation_file: path to annotation file temporarily saved via
        Slicer
        """
        dst = os.path.join(self._current_scan_folder,
                           self._current_scan.rstrip('.nii.gz') + '.json')
        print(f"saving: {dst}")
        copy(annotation_file, dst)

    def get_scan_folder(self):
        return self._current_scan_folder

    def load_volume(self):
        loaded_node = slicer.util.loadVolume(self._current_scan)
        return loaded_node.GetID()

    def load_annotation(self):
        loaded_node = slicer.util.loadMarkups(self._current_annotation)
        return loaded_node.GetID()
            
    def __next__(self):
        # Update the current scans
        self._current_scan_index += 1
        if self._current_scan_index >= len(self._scans):
            raise StopIteration
        self._current_scan = self._scans[self._current_scan_index]
        self._current_scan_folder = os.path.dirname(self._current_scan)

        self._current_annotation = self._current_scan.rstrip('.nii.gz') + '.json'
        if not os.path.isfile(self._current_annotation):
            self._current_annotation = None
        if self._skip_annotated and self.has_annotation():
            next(self)
        # print(self._current_scan)
        return self._current_scan, self._current_annotation
    
    def __exit__(self, exc_t, exc_va, exc_bt):
        return


class SimpleXNAT(ImageIterator):
    """
    Simple object to retrieve and store information to/from XNAT server
    """
    def __init__(self, server, user=None, pwd=None, xml_query_file=None):
        """
        Required input is the server URL and optionally username and password.
        The local netrc file is used if no credentials are provided
        :param server: XNAT server URL
        :param user: XNAT username
        :param pwd: XNAT password
        """
        super().__init__()
        self._patient = None
        self._filter = None
        self._server = server
        self._session = None
        if user is None or pwd is None:
            # Retrieve credential from netrc file
            user, _, pwd = netrc.netrc().authenticators(self._server)
        # Create a jsession with XNAT
        self._session = requests.Session()
        self._session.auth = (user, pwd)

        self._get_scans(xml_query_file)

    def __enter__(self):
        return self

    def _get_scans(self, filepath=None):
        """
        Performs an xnat search via the rest to retrieve the list of CT scans
        in MSKGSTT project. This is encoded in the xnat_scan_query.xml file.
        The list is stored as a pandas dataframe
        """
        # TODO Need to ensure path works from anywhere
        # Slicer changes working directory so relative paths fail
        if filepath is None or filepath == "":
            xml_query_file = os.path.join(os.path.curdir, 'xnat_scan_query.xml')
        else:
            xml_query_file = filepath

        url = '{}/data/search?format=csv'.format(self._server)
        raw_data = self._session.post(url,
                                      data=open(xml_query_file, 'rb')).text
        # print(raw_data)
        self._scans = pd.read_csv(StringIO(raw_data))
        self._filter = [True]*len(self._scans)

    def load_volume(self):
        """
        Based on the current scan folder, load the image into slicer.
        :return: ID of the node containing the loaded image
        """

        with DICOMUtils.TemporaryDICOMDatabase() as db:
            DICOMUtils.importDicom(self._current_scan_folder, db)
            # create loadable volumes from dicom
            slicer.modules.DICOMWidget.browserWidget.examineForLoading()
            # load volume
            loadedNodeIDs = DICOMUtils.loadPatientByName(self._patient)
            # store reference so volume can be deleted
            # self._currentImage = loadedNodeIDs[0]
            return loadedNodeIDs[0]

    def filter_scan(self, **kwargs):
        """
        Placeholder to perform filtering on the scan dataframe
        :param kwargs: header and filter operation
        """
        headers = ['subject_id',
                   'session_label',
                   'session_id',
                   'id',
                   'project',
                   'note',
                   'parameters_orientation',
                   'frames,bodypartexamined',
                   'parameters_imagetype',
                   'uid',
                   'series_description',
                   'quarantine_status']
        unknown_header = [k for k in kwargs.keys() if k not in headers]
        for k in unknown_header:
            del self
            raise KeyError('Unknown parameters for scan filtering:', k)
        raise NotImplementedError()

    def get_scan_folder(self):
        """
        Download locally the image of the current scan
        :return: path of the DICOM folder
        """
        # Set the filename of the zip file to download
        filename = self._current_scan_folder + '.zip'
        # Rest request to download the data
        url = '{}/data/projects/{}/subjects/{}/experiments/{}/scans/{}'.format(
            self._server,
            self._current_scan['project'].values[0],
            self._current_scan['subject_id'].values[0],
            self._current_scan['session_id'].values[0],
            self._current_scan['id'].values[0],
        )
        url += '/resources/DICOM/files?format=zip'

        # Save the file on disk
        r = self._session.get(url)
        with open(filename, 'wb') as f:
            f.write(r.content)
        # Unzip the downloaded file and ignore the folder structure
        with zipfile.ZipFile(filename) as zip:
            for zip_info in zip.infolist():
                if zip_info.filename[-1] == '/':
                    continue
                zip_info.filename = os.path.basename(zip_info.filename)
                zip.extract(zip_info, self._current_scan_folder)
        # Delete zip file
        os.remove(filename)
        # Returns folder that contains all the DICOM
        return self._current_scan_folder

    def delete_scan_dicom_folder(self):
        """
        Delete all information from disk on current scan
        """
        if self._current_scan_folder is not None and\
                os.path.exists(self._current_scan_folder):
            shutil.rmtree(self._current_scan_folder)
        self._current_scan_folder = None

    def store_annotations(self, annotation_file):
        """
        Upload annotation file (JSON) to XNAT as a resource associated with
        current scan.
        :param annotation_file: path to annotation file temporarily saved via
        Slicer
        """
        filename = '{}-{}.json'.format(
            self._current_scan['session_label'].values[0],
            self._current_scan['id'].values[0]
        )
        # annotation file is created by Slicer and its path is provided now
        # if not os.path.exists(self._current_scan_folder):
        #     os.mkdir(self._current_scan_folder)
        # with open(os.path.join(self._current_scan_folder, filename), 'w') as f:
        #     json.dump(annotation.to_json(), f)

        # Create a new resource associated with the scan
        url = '{}/data/projects/{}/subjects/{}/experiments/{}/scans/{}'.format(
            self._server,
            self._current_scan['project'].values[0],
            self._current_scan['subject_id'].values[0],
            self._current_scan['session_id'].values[0],
            self._current_scan['id'].values[0],
        )
        url += '/resources/ANNOTATIONS'
        self._session.put(url)
        # Upload the json file in the newly created resource
        url += '/files/{}'.format(filename)
        files = {'file': open(annotation_file, 'rb')}
        self._session.put(url, files=files)
        # os.remove(os.path.join(self._current_scan_folder, filename))

    def __next__(self):
        """
        Increment current scan represented as a dataframe row.
        Clean any information from disk related to previous scan
        :return: session name
        """
        # Delete the previous dicom data folder if it exists
        if self._current_scan_folder is not None:
            self.delete_scan_dicom_folder()
        # Update the current scans
        # if i >= len(self._scans.index):
        #     raise StopIteration
        self._current_scan_index += 1
        if self._current_scan_index >= len(self._scans[self._filter]):
            raise StopIteration()
        i = self._current_scan_index
        # self._current_scan = self._scans.iloc[[i]]
        self._current_scan = self._scans[self._filter].iloc[[i]]
        # Set the folder required to save data
        session = self._current_scan['session_label'].values[0]
        foldername = f"{session}-{self._current_scan['id'].values[0]}"
        self._current_scan_folder = os.path.join(tempfile.mkdtemp(),
                                                 foldername)
        self._patient = session.split("_", 1)[0]

        # ToDo: Check whether there is an annotation file in xnat, then load it
        #   and return the path to the local file
        # return session, annotation_file

        return session

    def __exit__(self, exc_t, exc_va, exc_bt):
        """
        Ensure data is cleaned up and xnat session is closed
        when leaving context
        :param exc_t: exception type
        :param exc_va: exception value
        :param exc_bt: exception backtrace
        """
        # Delete current dicom folder to clean up
        self.delete_scan_dicom_folder()
        # Ensures the jsession is closed upon finishing
        self._session.close()
        self._session.delete(f'{self._server}/data/JSESSION')


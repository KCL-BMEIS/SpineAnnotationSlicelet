from io import StringIO
import pandas as pd
import requests
import tempfile
import zipfile
import shutil
import netrc
import json
import os


class SimpleXNAT:
    """
    Simple object to retrieve and upload information to/from XNAT server
    """
    def __init__(self, server, user=None, pwd=None, xml_query_file=None):
        """
        Required input is the server URL and optionally username and password.
        The local netrc file is used if no credentials are provided
        :param server: XNAT server URL
        :param user: XNAT username
        :param pwd: XNAT password
        """
        self._server = server
        self._session = None
        self._scans = None
        self._current_scan = None
        self._current_scan_folder = None
        if user is None or pwd is None:
            # Retrieve credential from netrc file
            user, _, pwd = netrc.netrc().authenticators(self._server)
        # Create a jsession with XNAT
        self._session = requests.Session()
        self._session.auth = (user, pwd)
        # Download the list of scan from XNAT
        self._update_scan_list(xml_query_file)

    def __enter__(self):
        return self

    def _update_scan_list(self, filepath=None):
        """
        Performs an xnat search via the rest to retrive the list of CT scans
        in MSKGSTT project. This is encoded in the xnat_scan_query.xml file.
        The list in stored as a pandas dataframe
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

    def filter_scan(self, **kargs):
        """
        Placeholder to perform filtering on the scan dataframe
        :param args: header and filter operation
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
        unknown_header = [k for k in args.keys() if k not in headers]
        for k in unknown_header:
            del self
            raise KeyError('Unknown parameters for scan filtering:', k)
        raise NotImplementedError()

    def get_scan_dicom_folder(self):
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

    def upload_annotations(self, annotation_file):
        """
        Upload annotation file (JSON) to XNAT as a resource associated with
        current scan.
        """
        # Save the annotation to disk as a json file
        filename = '{}-{}.json'.format(
            self._current_scan['session_label'].values[0],
            self._current_scan['id'].values[0]
        )
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

    def __iter__(self):
        """
        Initialise the iterator to first scan in the data frame
        :return: self
        """
        self._current_scan_index = 0
        return self

    def __next__(self):
        """
        Increment current scan represented as a dataframe row.
        Clean any information from disk related to previous scan
        :return: Dataframe single row
        """
        # Delete the previous dicom data folder if it exists
        if self._current_scan_folder is not None:
            self.delete_scan_dicom_folder()
        # Update the current scans
        i = self._current_scan_index
        if i >= len(self._scans.index):
            raise StopIteration
        self._current_scan_index += 1
        self._current_scan = self._scans.iloc[[i]]
        # Set the folder required to save data
        filename = '{}-{}.json'.format(
            self._current_scan['session_label'].values[0],
            self._current_scan['id'].values[0]
        )
        self._current_scan_folder = os.path.join(tempfile.gettempdir(),
                                                 filename)
        return self._current_scan

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
        self._session.delete('{}/data/JSESSION'.format(self._server))
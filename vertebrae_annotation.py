import json


class VertebraeAnnotations:
    def __init__(self, project, subject_label, session_label, scan_id):
        self._project = project
        self._subject_label = subject_label
        self._session_label = session_label
        self._scan_id = scan_id
        # List of all relevant labels
        labels = ('C1', 'C2', 'C3',
                  'T1', 'T2', 'T3',
                  'L1', 'L2', 'L3',
                  'S1', 'S2', 'S3')
        # Dictionary to store x, y, z coordinate
        self._annotations = dict.fromkeys(labels, (None, None, None))

    def get_labels(self):
        return self._annotations.keys()

    def set_coordinate(self, label, x, y, z):
        if label not in self.get_labels():
            raise KeyError('Unknown label', label)
        self._annotations[label] = (x, y, z)

    def get_coordinate(self, label):
        if label not in self.get_labels():
            raise KeyError('Unknown label', label)
        return self._annotations[label]

    def to_json(self):
        json_object = json.dumps(
            {
                'project': self._project,
                'subject': self._subject_label,
                'session': self._session_label,
                'scan': self._scan_id,
                'annotations': self._annotations
            },
        )
        return json_object

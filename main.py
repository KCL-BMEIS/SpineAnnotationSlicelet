from xnat import SimpleXNAT
from vertebrae_annotation import VertebraeAnnotations

if __name__ == '__main__':
    # Create an object to recovered the list of scan
    with SimpleXNAT('https://int-xnat01.isd.kcl.ac.uk') as scans_list:

        for s in scans_list:
            test = VertebraeAnnotations('test', 'sub', 'sess', 'scan')
            print(s)
            scans_list.upload_annotations(test)
            break

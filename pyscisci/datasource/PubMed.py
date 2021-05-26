import os
import sys
import json
import gzip

import pandas as pd
import numpy as np
from nameparser import HumanName
import requests
import ftplib
from lxml import etree
from io import BytesIO

# determine if we are loading from a jupyter notebook (to make pretty progress bars)
if 'ipykernel' in sys.modules:
    from tqdm.notebook import tqdm
else:
    from tqdm import tqdm


from pyscisci.datasource.readwrite import load_preprocessed_data, load_int, load_float, load_html_str, load_xml_text
from pyscisci.database import BibDataBase

class PubMed(BibDataBase):
    """
    Base class for PubMed Medline interface.

    ==========
    Notes
    ==========
    ~ PubMed comes as >1000 compressed XML files.
    ~ The PMID is renamed PublicationId to be consistent with the rest of pySciSci.
    ~ PubMed does not disambiguate Authors.
    ~ 
    """


    def __init__(self, path2database='', keep_in_memory=False, global_filter=None, show_progress=True):

        self._default_init(path2database, keep_in_memory, global_filter, show_progress)

        self.PublicationIdType = int
        self.AffiliationIdType = int
        self.AuthorIdType = str


    def _blank_pubmed_publication(self, PublicationId = 0):
        record = {}
        record['PublicationId'] = PublicationId
        record['Title'] = ''
        record['Year'] = 0
        record['Volume'] = 0
        record['Issue'] = ''
        record['Pages'] = ''
        record['JournalId'] = ''
        record['TeamSize'] = 0
        record['Month'] = 1
        record['Day'] = 1
        record['ISSN'] = ''
        record['Doi'] = ''

        return record

    def _blank_pubmed_author(self):
        record = {}
        record['FullName'] = ''
        record['FirstName'] = ''
        record['LastName'] = ''
        record['Affiliations'] = ''
        record['AuthorSequence'] = 0
        return record

    def _save_dataframes(self, ifile, publication_df, paa_df, pub2ref_df, pub2field_df):

        publication_df = pd.DataFrame(publication_df)
        publication_df['PublicationId'] = publication_df['PublicationId'].astype(int)
        publication_df['Year'] = publication_df['Year'].astype(int)
        publication_df['Month'] = publication_df['Month'].astype(int)
        publication_df['Day'] = publication_df['Day'].astype(int)
        publication_df['Volume'] = pd.to_numeric(publication_df['Volume'])
        publication_df['TeamSize'] = publication_df['TeamSize'].astype(int)
        publication_df.to_hdf( os.path.join(self.path2database, self.path2pub_df, 'publication{}.hdf'.format(ifile)), key = 'pub', mode='w')


        paa_df = pd.DataFrame(paa_df)
        paa_df['AuthorSequence'] = paa_df['AuthorSequence'].astype(int)
        paa_df.to_hdf( os.path.join(self.path2database, self.path2paa_df, 'publicationauthoraffiliation{}.hdf'.format(ifile)), key = 'paa', mode='w')

        pub2field_df = pd.DataFrame(pub2field_df, columns = ['PublicationId', 'FieldId'], dtype=int)
        pub2field_df.to_hdf( os.path.join(self.path2database, self.path2pub2field_df, 'pub2field{}.hdf'.format(ifile)), key = 'pub2field', mode='w')

        pub2ref_df = pd.DataFrame(pub2ref_df, columns = ['CitedPublicationId', 'CitingPublicationId', 'Citation'], dtype=int)
        pub2ref_df.to_hdf( os.path.join(self.path2database, self.path2pub2ref_df, 'pub2ref{}.hdf'.format(ifile)), key = 'pub2ref', mode='w')

    def preprocess(self, xml_directory = 'RawXML', process_name=True, num_file_lines=10**6, show_progress=True):
        """
        Bulk preprocess of the PubMed raw data.

        Parameters
        ----------
        :param process_name: bool, default True
            If True, then when processing the raw file, the package `NameParser <https://nameparser.readthedocs.io/en/latest/>`_
            will be used to split author FullNames.

        :param num_file_lines: int, default 10**6
            The processed data will be saved into smaller DataFrames, each with `num_file_lines` rows.

        :param show_progress: bool, default True
            Show progress with processing of the data.

        """

        if show_progress:
            print("Starting to preprocess the PubMed database.")

        for hier_dir_type in [self.path2pub_df, self.path2paa_df, self.path2pub2field_df, self.path2pub2ref_df, self.path2fieldinfo_df]:

            if not os.path.exists(os.path.join(self.path2database, hier_dir_type)):
                os.mkdir(os.path.join(self.path2database, hier_dir_type))


        xmlfiles = sorted([fname for fname in os.listdir(os.path.join(self.path2database, xml_directory)) if '.xml' in fname])

        # read dtd - this takes
        path2database = self.path2database # remove self to use inside of this class
        class DTDResolver(etree.Resolver):
            def resolve(self, system_url, public_id, context):
                return self.resolve_filename(os.path.join(path2database, system_url), context)
        parser = etree.XMLParser(load_dtd=True, resolve_entities=True)

        pub2year = {}
        fieldinfo = {}

        ifile = 0
        for xml_file_name in tqdm(xmlfiles, desc='PubMed xml files', leave=True, disable=not show_progress):
            
            publication_df = []
            paa_df = []
            pub2field_df = []
            pub2ref_df = []

            xmltree = etree.parse(os.path.join(self.path2database, xml_directory, xml_file_name), parser)
            
            all_pubmed_articles = xmltree.findall("/PubmedArticle")
            
            for article_bucket in all_pubmed_articles:

                medline = article_bucket.find("MedlineCitation")
                
                # scrape the publication information
                PublicationId = load_int(load_xml_text(medline.find('PMID')))
                pub_record = self._blank_pubmed_publication(PublicationId)

                article = medline.find("Article")
                pub_record['Title'] = load_html_str(load_xml_text(article.find('ArticleTitle')))
                pub_record['Pages'] = load_html_str(load_xml_text(article.find('Pagination').find("MedlinePgn")))


                journal = article.find("Journal")
                pub_record['JournalId'] = load_html_str(load_xml_text(journal.find("Title")))
                pub_record['Volume'] = load_int(load_xml_text(journal.find("JournalIssue").find("Volume")))
                pub_record['Issue'] = load_int(load_xml_text(journal.find("JournalIssue").find("Issue")))
                pub_record['ISSN'] = load_html_str(load_xml_text(journal.find("ISSN")))
                
                history = article_bucket.find("PubmedData/History")
                if not history is None:
                    pdate = history.find('PubMedPubDate[@IdType="medline"]')
                    if not pdate is None:
                        pub_record['Year'] = load_int(load_xml_text(pdate.find("Year")))
                        pub_record['Month'] = load_int(load_xml_text(pdate.find("Month")))
                        pub_record['Day'] = load_int(load_xml_text(pdate.find("Day")))
                

                if pub_record['Year'] > 0:
                    pub2year[PublicationId] = pub_record['Year']

                article_ids = article_bucket.find("PubmedData/ArticleIdList")
                if article_ids is not None:
                    doi = article_ids.find('ArticleId[@IdType="doi"]')
                    pub_record['Doi'] = load_xml_text(doi)


                author_list = article.find('AuthorList')

                if not author_list is None:
                    for seq, author in enumerate(author_list.findall('Author')):
                        author_record = self._blank_pubmed_author()

                        author_record['FirstName'] = load_html_str(load_xml_text(author.find("ForeName")))
                        author_record['LastName'] = load_html_str(load_xml_text(author.find("LastName")))
                        author_record['FullName'] = author_record['FirstName'] + ' ' + author_record['LastName']

                        if author.find("AffiliationInfo/Affiliation") is not None:
                            author_record['Affiliations'] = load_html_str(load_xml_text(author.find("AffiliationInfo/Affiliation")))
                            author_record['Affiliations'] = author_record['Affiliations'].replace("For a full list of the authors' affiliations please see the Acknowledgements section.","")
                    
                        author_record['AuthorSequence'] = seq+1

                        paa_df.append(author_record)

                    pub_record['TeamSize'] = seq + 1

                meshterms = medline.find("MeshHeadingList")

                if meshterms is not None:
                    for term in meshterms.getchildren():
                        ui = term.find("DescriptorName").attrib.get("UI", "")
                        if len(ui)>0:
                            pub2field_df.append([PublicationId, ui])
                            fieldinfo[ui] = [load_xml_text(term.find("DescriptorName")), 'mesh']

                chemicals = medline.find("ChemicalList")
                if chemicals is not None:
                    for chemical in chemicals.findall("Chemical"):
                        ui = chemical.find("NameOfSubstance").attrib.get("UI", "")
                        if len(ui)>0:
                            pub2field_df.append([PublicationId, ui])
                            fieldinfo[ui] = [ui, load_xml_text(chemical.find("NameOfSubstance")), 'chem']
                
                references = article_bucket.find("PubmedData/ReferenceList")
                if not references is None:
                    for ref in references.findall("Reference"):
                        citation = load_xml_text(ref.find("Citation"))
                        if not ref.find('ArticleIdList') is None:
                            pmid = load_int(load_xml_text(ref.find('ArticleIdList').find('ArticleId[@IdType="pubmed"]')))
                        else:
                            pmid = ""
                        pub2ref_df.append([PublicationId, pmid, citation])

                publication_df.append(pub_record)

            self._save_dataframes(ifile, publication_df, paa_df, pub2ref_df, pub2field_df)
            ifile += 1

        fieldinfo = pd.DataFrame(list(fieldinfo.values()), columns = ['FieldId', 'FieldName', 'FieldType'], dtype=int)
        fieldinfo.to_hdf( os.path.join(self.path2database, self.path2fieldinfo_df, 'fieldinfo{}.hdf'.format(ifile)), key = 'fieldinfo', mode='w')

        with gzip.open(os.path.join(self.path2database, 'pub2year.json.gz'), 'w') as outfile:
            outfile.write(json.dumps(pub2year).encode('utf8'))


    def download_from_source(self, source_url='ftp.ncbi.nlm.nih.gov', dtd_url = 'https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_190101.dtd',
        rewrite_existing = False, show_progress=True):
        """
        Download the Pubmed raw xml files and the dtd formating information from [PubMed](https://www.nlm.nih.gov/databases/download/pubmed_medline.html).
            1. pubmed/baseline - the directory containing the baseline compressed xml files
            2. pubmed_190101.dtd - the dtd containing xml syntax

        The files will be saved to the path specified by `path2database` into RawXML.

        Parameters
        ----------
        :param source_url: str, default 'ftp.ncbi.nlm.nih.gov'
            The base url for the ftp server from which to download.

        :param dtd_url: str, default 'pubmed_190101.dtd'
            The url for the dtd file.

        :param show_progress: bool, default True
            Show progress with processing of the data.

        """

        FTP_USER = "anonymous"
        FTP_PASS = ""

        ftp = ftplib.FTP(source_url, FTP_USER, FTP_PASS)
        ftp.encoding = "utf-8"
        ftp.cwd("pubmed/baseline/")

        files2download = sorted([fname for fname in ftp.nlst() if '.xml.gz' in fname and not '.md5' in fname])
        
        if not os.path.exists(os.path.join(self.path2database, 'RawXML')):
            os.mkdir(os.path.join(self.path2database, 'RawXML'))

        if not rewrite_existing:
            files_already_downloaded = os.listdir(os.path.join(self.path2database, 'RawXML'))
            files2download = [fname for fname in files2download if not fname in files_already_downloaded]

        for xml_file_name in tqdm(files2download, disable=not show_progress):
            with open(os.path.join(self.path2database, 'RawXML', xml_file_name), "wb") as outfile:
                ftp.retrbinary('RETR %s' % xml_file_name, outfile.write)

        with open(os.path.join(self.path2database, 'RawXML', 'pubmed_190101.dtd'), 'w') as outfile:
            outfile.write(requests.get(dtd_url).content.decode('utf-8'))

        ftp.quit()
            

    def parse_affiliations(self, preprocess = False):
        raise NotImplementedError("PubMed artciles are stored with all information in an xml file.  Run preprocess to parse the file.")

    def parse_authors(self, preprocess = False, process_name = True, num_file_lines = 5*10**6):
        raise NotImplementedError("PubMed artciles are stored with all information in an xml file.   Run preprocess to parse the file.")

    def parse_publications(self, preprocess = False, num_file_lines=10**7):
        raise NotImplementedError("PubMed artciles are stored with all information in an xml file.   Run preprocess to parse the file.")

    def parse_references(self, preprocess = False, num_file_lines=10**7):
        raise NotImplementedError("PubMed does not contain reference or citation information.")

    def parse_publicationauthoraffiliation(self, preprocess = False, num_file_lines=10**7):
        raise NotImplementedError("PubMed artciles are stored with all information in an xml file.  Run preprocess to parse the file.")

    def parse_fields(self, preprocess = False, num_file_lines=10**7):
        raise NotImplementedError("PubMed does not contain field information.")



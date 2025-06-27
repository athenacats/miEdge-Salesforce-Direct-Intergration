import streamlit as st
import pandas as pd
import re
import requests
from simple_salesforce import Salesforce
import io
import warnings
import os

st.set_page_config(
    page_title="ESI miEdge-Salesforce Integration",  # This sets the title in the browser tab
    page_icon="https://www.eesipeo.com/media/logoicon-copy-2-1.svg"  # This sets the favicon (can be an emoji or image URL)
)




warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# Suppress Streamlit specific warnings
st.set_option('client.showErrorDetails', False)


# =======================
# Salesforce OAuth2 Details (Hardcoded)
# =======================

CLIENT_ID = st.secrets["salesforce"]["client_id"]
CLIENT_SECRET = st.secrets["salesforce"]["client_secret"]

REDIRECT_URI = 'https://esi-miedge-salesforce-direct-intergration.streamlit.app'
AUTH_URL = 'https://login.salesforce.com/services/oauth2/authorize'
TOKEN_URL = 'https://login.salesforce.com/services/oauth2/token'
# AUTH_URL = 'https://test.salesforce.com/services/oauth2/authorize'
# TOKEN_URL = 'https://test.salesforce.com/services/oauth2/token'

# =======================
# Helper Function to Initiate OAuth2 Flow (Meta Refresh Redirect)
# =======================
def initiate_salesforce_auth():
    auth_link = f"{AUTH_URL}?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}"
    st.write(f"[🔗 Click here to connect to Salesforce]({auth_link})")

def get_valid_picklist_values(sf_instance, object_name, field_name):
    describe = sf_instance.__getattr__(object_name).describe()
    for field in describe['fields']:
        if field['name'] == field_name:
            valid_values = set(value['value'] for value in field['picklistValues'])
            st.write(f"✅ Valid values for `{field_name}`: {valid_values}")  # This goes to the Streamlit app interface
            return valid_values
    return set()


# =======================
# Function to Exchange Auth Code for Access Token
# =======================
def get_salesforce_token(auth_code):
    data = {
        'grant_type': 'authorization_code',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': auth_code,
        'redirect_uri': REDIRECT_URI
    }

    response = requests.post(TOKEN_URL, data=data)
    if response.status_code == 200:
        token_data = response.json()
        st.success("✅ Successfully authenticated with Salesforce!")
        
        sf_instance = Salesforce(instance_url=token_data['instance_url'], session_id=token_data['access_token'])
        st.session_state['salesforce'] = sf_instance  # 💾 Save Salesforce connection

        valid_providers = get_valid_picklist_values(sf_instance, 'Lead', 'Current_Provider__c')
        
        st.session_state['valid_providers'] = valid_providers
       
        return sf_instance
    else:
        st.error(f"❌ Salesforce Authentication Failed: {response.text}")
        return None

# =======================
# Helper Function to Detect C-Level Titles
# =======================
def is_executive_title(title):
    patterns = [
        r'\bCEO\b', r'\bCFO\b', r'\bCTO\b', r'\bCIO\b', r'\bCOO\b', r'\bPresident\b',  r'\bCAO\b', r'\bOwner\b', r'\bCMO\b', r'\bCHRO\b', r'\bCLO\b', r'\bCPO\b', r'\bCRO\b', r'\bFounder\b', r'\bChairman\b', r'\bMD\b']

    exclusion_patterns = [
        r'\bHR\b', r'\bHuman Resources\b', r'\barchitect\b', r'\bcreative\b', r'\bcontent\b', r'\binnovation\b', r'\bscientist\b', r'\bnurse\b', r'\bmedical\b', r'\bpeople\b', r'\bPayroll\b', r'\bBenefits\b', r'\bAccounting\b', r'\bConstruction\b', r'\bEngineer\b', r'\bengineering\b', r'\bclinical\b',
        r'\blending\b', r'\bresearch\b', r'\bclient\b', r'\bengine\b', r'\blearning\b', r'\bgovernment\b', r'\bloan\b',
        r'\bmember\b', r'\btechnical\b', r'\bproperty\b', r'\bpolicy\b', r'\brevenue\b', r'\bgeology\b', r'\banalyst\b',
        r'\baccountant\b', r'\bhealthcare\b', r'\bhealth\b', r'\bsecurity\b', r'\bcloud\b', r'\bclinic\b', r'\blegal\b', r'\bdrug\b', r'\bdiversity\b',
        r'\bleasing\b', r'\bpastry\b', r'\butilities\b', r'\btreasurer\b', r'\bcontract\b', r'\blisting\b', r'\bgrants\b',
        r'\bleadership\b', r'\bsports\b', r'\bquality\b', r'\btoxicology\b', r'\bpulmonary\b', r'\bmanufacturer\b',
        r'\bindustry\b', r'\bchemistry\b', r'\bbiology\b', r'\blaboratory\b', r'\bspace\b', r'\bexecutive administrator\b',
        r'\bpulmonary\b', r'\bvirtual\b', r'\bquality\b', r'\bphaermaceuticl\b', r'\bscience\b', r'\bsciences\b', r'\bprofessional\b',
        r'\bparalegal\b', r'\bmembership\b', r'\bdonor\b', r'\bcurriculum\b', r'\bbioanalytics\b'
    ]

    if any(re.search(pattern, str(title), re.IGNORECASE) for pattern in patterns):
        if not any(re.search(excl_pattern, str(title), re.IGNORECASE) for excl_pattern in exclusion_patterns):
            return True

    return False

# =======================
# Function to Push Data to Salesforce
# =======================
import streamlit as st
import time  # For simulating delays in progress

def clean_date(date_str):
    if pd.isna(date_str) or date_str.strip() == '':
        return None  # Salesforce accepts null dates
    try:
        # Try parsing date from various formats
        parsed_date = pd.to_datetime(date_str, errors='coerce')
        if pd.isna(parsed_date):
            return None
        return parsed_date.strftime('%Y-%m-%d')  # Convert to YYYY-MM-DD
    except Exception as e:
        st.warning(f"⚠️ Could not parse date: {date_str}")
        return None


def push_to_salesforce(sf_instance, df, selected_object):

    
    st.session_state.sales_users = get_active_sales_users(sf_instance)
    st.session_state.round_robin_index = 0  # Start from the first user
    st.write("📋 Final Round Robin Users:", st.session_state.sales_users)


    sales_users = st.session_state.sales_users
    total_users = len(sales_users)
    st.write("📋 Total Users:", total_users)

    assign_owner = total_users > 0
    
    df_cleaned = df.fillna('')

    total_records = len(df_cleaned)
    success_count = 0
    failed_count = 0
    duplicate_count = 0

    progress_bar = st.progress(0)
    status_text = st.empty()
    success_counter = st.empty()
    duplicate_counter = st.empty()
    failed_counter = st.empty()
    failed_messages = []

    status_text.text("🚀 Starting upload to Salesforce... PLEASE KEEP THIS WINDOW OPEN DURING THE OPERATION! If the session disconnects at any point, just click on the '🚀 Push Filtered Data to Salesforce' button again")

    for idx, (_, row) in enumerate(df_cleaned.iterrows()):
        # Extract and map fields from DataFrame
        if assign_owner:
            owner_id = sales_users[st.session_state.round_robin_index]
            st.session_state.round_robin_index = (st.session_state.round_robin_index + 1) % total_users
            st.write("📋 Owner id", owner_id)
            if owner_id == "0051U00000AVuYnQAL":
                st.warning("⚠️ Skipping Barry (0051U00000AVuYnQAL) as lead owner.")
                continue
        else:
            owner_id = "0051U00000AZSVcQAP"
            st.warning("⚠️ No valid Salesforce users for round robin assignment. Default owner will be used (likely whoever connected OAuth).")
        st.write("📋 Owner id2", owner_id)
        Salutation = row.get('Contact Prefix (e.g. Dr, Prof etc.)', '') or ''
        first_name = row.get('Contact First Name', '') or ''
        MiddleName = row.get('Contact Middle Name (or initial)', '') or ''
        last_name = row.get('Contact Last Name', '') or ''
        company = row.get('Contact Company name', '') or 'Unknown'
        email = row.get('Contact Email', '') or ''
        phone = row.get('Contact Phone Number', '') or ''
        job_title = row.get('Job Title', '') or ''
        valid_providers = st.session_state.get('valid_providers', set())
        current_provider = row.get('PEO (Normalized)', '').strip()
        Current_Provider__c = current_provider if current_provider in valid_providers else 'Unknown' #check on this
        NumberOfEmployees = row.get('Employees', '') or ''
        website = row.get('Website', '') or ''
        industry = (row.get('Industry', '') or '')[:255] #picklist
        Company_Phone__c = row.get('Phone Number', '') or ''
        LinkedIn__c = row.get('LinkedIn', '') or ''
        LeadSourceOther = row.get('PEO (Normalized)', '') or ''
        # Address = row.get('Address 1', '') or ''
        Facebook__c = row.get('Facebook', '') or ''
        Twitter__c = row.get('Twitter', '') or ''
        # msid__c = row.get('MSID', '') or ''
        naics_Description__c = row.get('NAICS Description', '')[:150] or ''
        Company_NAICS_Code__c = row.get('NAICS Code', '') or ''
        osha = row.get('OSHA', '') or ''
        whd = row.get('WHD', '') or ''
        Fidelity_Bond__c = row.get('Fidelity Bond', '') or ''
        Revenue_Range__c = row.get('Revenue Range', '') or ''
        Benefits_Broker__c = row.get('Benefits Broker', '') or ''
        Accounting_Firm__c = row.get('Accounting Firm', '') or ''
        Workers_Compensation_Carrier__c = row.get("Workers' Compensation Carrier", '') or ''
        Workers_Comp_Renewal_Date__c = clean_date(row.get("Workers' Compensation Renewal Date", '') or '')
        bipd = row.get("BIPD Carrier", '') or ''
        bipd_renewal = clean_date(row.get("BIPD Renewal", '') or '')
        Bond_Carrier__c = row.get("Bond Carrier", '') or ''
        Bond_Renewal__c = clean_date(row.get("Bond Renewal", '') or '')
        Business_Travel__c = row.get("Business Travel", '') or ''
        Business_Travel_Carrier__c = row.get("Business Travel Carrier", '') or ''
        Business_Travel_Renewal__c = clean_date(row.get("Business Travel Renewal", '') or '')
        Actuary_Name__c = row.get("Actuary Name", '') or ''
        Actuary_Firm_Name__c = row.get("Actuary Firm Name", '') or ''
        Motor_Carrier_Operation__c = row.get("Motor Carrier Operation", '') or ''
        Drivers__c = row.get('Drivers', '') or ''
        Mileage__c = row.get('Mileage', '') or ''
        dot = row.get('DOT', '') or ''
        Ex_Mod__c = row.get('Ex. Mod.', '') or ''
        Ex_Mod_changed_in_last_30_days__c = row.get('Ex Mod changed in last 30 days', '') or ''
        # Prepare data payload for Salesforce
        data = {
            'Salutation': Salutation,
            'FirstName': first_name,
            'MiddleName': MiddleName,
            'LastName': last_name,
            'Company': company,
            'Email': email,
            'Phone': phone,
            'Title': job_title,
            'LeadSource': 'miEdge',
            'OwnerId': owner_id,
            'Current_Provider__c': Current_Provider__c,
            'NumberOfEmployees': NumberOfEmployees,
            'Website': website,
            'Industry': industry,
            'Company_Phone__c': Company_Phone__c,
            'LinkedIn__c': LinkedIn__c,
            'Street': row.get('Contact Address', '') or '',
            'City': row.get('Contact City', '') or '',
            'State': row.get('Contact State', '') or '',
            'PostalCode': f"{row.get('Contact Zip', '')}-{row.get('Contact Zip4', '')}" if row.get('Contact Zip4', '') else row.get('Contact Zip', ''),
            'Facebook__c': Facebook__c,
            'Twitter__c': Twitter__c,
            'NAICS_Description__c': naics_Description__c,
            'Primary_NAICS__c': Company_NAICS_Code__c,
            'OSHA__c': osha,
            'Lead_Source_Other__c': LeadSourceOther,
            'WHD__c': whd,
            'Fidelity_Bond__c': Fidelity_Bond__c,
            'Revenue_Range__c': Revenue_Range__c,
            'Benefits_Broker__c': Benefits_Broker__c,
            'Accounting_Firm__c': Accounting_Firm__c,
            'Workers_Compensation_Carrier__c': Workers_Compensation_Carrier__c,
            'Workers_Comp_Renewal_Date__c': Workers_Comp_Renewal_Date__c,
            'BIPD_Carrier__c': bipd,
            'BIPD_Renewal__c': bipd_renewal,
            'Bond_Carrier__c': Bond_Carrier__c,
            'Bond_Renewal__c': Bond_Renewal__c,
            'Business_Travel__c': Business_Travel__c,
            'Business_Travel_Carrier__c': 	Business_Travel_Carrier__c,
            'Business_Travel_Renewal__c': Business_Travel_Renewal__c,
            'Actuary_Name__c': Actuary_Name__c,
            'Actuary_Firm_Name__c': Actuary_Firm_Name__c,
            'Motor_Carrier_Operation__c': Motor_Carrier_Operation__c,
            'Drivers__c': Drivers__c,
            'Mileage__c': Mileage__c,
            'DOT__c': dot,
            'Ex_Mod__c': Ex_Mod__c,
            'Ex_Mod_changed_in_last_30_days__c': Ex_Mod_changed_in_last_30_days__c,

        }   

        try:
            st.write(f"➡️ Assigning lead to user: {owner_id}")
            # Push data to Salesforce
            #sf_instance.__getattr__(selected_object).create(data)
            success_count += 1

        except Exception as e:
            error_message = str(e)

            # Handle duplicate errors
            if 'DUPLICATES_DETECTED' in error_message:
                duplicate_count += 1
            else:
                failed_count += 1
                failed_messages.append(f"Row {idx+1}: {error_message}")

        # Update dynamic counters and progress
        progress = min((idx + 1) / total_records, 1.0)
        progress_bar.progress(progress)

        success_counter.markdown(f"✅ **Successful Uploads:** {success_count}")
        duplicate_counter.markdown(f"⚠️ **Duplicates Skipped:** {duplicate_count}")
        failed_counter.markdown(f"❌ **Failed Records:** {failed_count}")

        # Simulate delay for demonstration purposes (remove in production)
        time.sleep(0.1)

    # Final status
    status_text.text("✅ Upload Complete!")

    # Display final counts
    st.success(f"✅ Successfully pushed {success_count} records to Salesforce.")
    if duplicate_count > 0:
        st.warning(f"⚠️ Skipped {duplicate_count} duplicate records.")
    if failed_count > 0:
        st.error(f"❌ {failed_count} records failed due to other errors.")
        with st.expander("🛠 See Details for Failed Records"):
            st.text("\n".join(failed_messages))

def job_title_selector(df):
    st.write("### 🛠 Select Job Titles to Keep")

    # Extract unique job titles
    unique_job_titles = sorted(df['Job Title'].dropna().unique().tolist())
    unique_peos = sorted(df['PEO (Normalized)'].dropna().unique().tolist())

    # Pre-select executive titles
    preselected_titles = [title for title in unique_job_titles if is_executive_title(title)]
    unselected_titles = [title for title in unique_job_titles if title not in preselected_titles]

    # Add emojis for visual distinction
    preselected_titles_display = [f" {title}" for title in preselected_titles]
    unselected_titles_display = [f" {title}" for title in unselected_titles]

    # Combine lists to show preselected on top
    combined_titles_display = preselected_titles_display + unselected_titles_display
    combined_titles_values = preselected_titles + unselected_titles

    preselected_peos = unique_peos

    # Apply custom CSS for scrollable multiselect dropdown
    st.markdown("""
        <style>
        /* Limit the height of the multiselect dropdown menu */
        .stMultiSelect > div {
            max-height: 50vh;
            overflow-y: auto;
        }
        /* Ensure the expander content scrolls within its area */
        .stExpanderContent {
            max-height: 55vh;
            overflow-y: auto;
        }
                
        .stMultiSelect div[role='listbox'] span {
            margin-bottom: 4px;  
            padding: 6px 10px;   
            display: block;       
            border-radius: 4px;   
        }
        </style>
    """, unsafe_allow_html=True)

    # Create a mapping between displayed titles and original titles
    display_to_title = dict(zip(combined_titles_display, combined_titles_values))

    # Use expander for dropdown effect
    with st.expander(f"🔽 Show/Hide Job Titles ({len(preselected_titles)} pre-selected)"):
        selected_display_titles = st.multiselect(
            "✅ Pre-selected C-Level and Executive Titles. To add a title, click anywhere in the dropdown. To remove a title, click X",
            options=combined_titles_display,  # All titles shown with emojis
            default=preselected_titles_display,  # Preselect executive titles
            key="job_titles"
        )

    with st.expander(f"🔽 PEO (Normalized) Filter - ({len(preselected_peos)} pre-selected)"):
        selected_peos = st.multiselect(
            "✅ Select PEOs to Include:",
            options=unique_peos,
            default=preselected_peos,
            key="peo_filter"
        )

    # Map back selected display titles to original titles
    selected_titles = [display_to_title[title] for title in selected_display_titles]

    st.write(f" **Selected: {len(selected_titles)} Job Titles**")
    st.write(f"✅ {len(selected_peos)} PEOs selected.")
    return selected_titles, selected_peos

def get_active_sales_users(sf_instance):
    query = """
    SELECT Id, Name FROM User
    WHERE Profile.Name = 'Sales User' AND IsActive = TRUE
    """
    results = sf_instance.query_all(query)

    users = results['records']
    excluded_names = {"Terry Hookstra", "Terry Nagelkirk"}
    filtered_users = [user['Id'] for user in users if user['Name'] not in excluded_names]

    return filtered_users


# =======================
# Main Streamlit App
# =======================
def main():
    st.markdown("""
        <div style="display: flex; align-items: center; gap: 12px;">
            <img src="https://www.eesipeo.com/media/1-eESI_Logo_RevOut-1-4.png" alt="ESI Logo" width="100" height="auto">
            <h1 style="margin: 0;">ESI miEdge-Salesforce Integration</h1>
        </div>
    """, unsafe_allow_html=True)

    st.write("Authenticate with **Salesforce** first, then upload your **CSV** file and push data.")

    

    

    st.markdown("""
        <style>
        div.stButton > button:first-child {
            background-color: #34dfa9 !important;
            color: black !important;
            font-weight: bold;
            border-radius: 8px;
            border: none;
            height: 40px;
            width: 100%;
        }
                
        .stToolbarActions.st-emotion-cache-1p1m4ay.e1i26tt72 {
            display: none;
        }
        .st-emotion-cache-14553y9.egexzqm0 {
            color:  #34dfa9 !important;
        }
                
        #MainMenu {
         visibility: hidden;
                }
        footer {
                visibility: hidden !important;
        }
                
        footer:after {
            content: " ";  /* You could even inject your own custom footer text here if you want */
            visibility: visible;
            display: block;
            position: relative;
            padding: 5px;
            text-align: center;
        }
        header {
                visibility: hidden;
        }
                
        [data-testid="stToolbar"] {
                visibility: hidden !important;
                }
            
                
                
        ._container_gzau3_1 {
            display: none !important;
        }

        ._profilePreview_gzau3_63 {
            display: none !important;
        }

        .st-emotion-cache-b0y9n5:hover {
            border: 1px solid #34dfa9 !important;
                }
        .st-ci {
            background-color: #34dfa9 !important;
        }
        .st-ch {
            color: black;
        }
        .stExpander.st-emotion-cache-0.e1kosxz20:hover .st-emotion-cache-1b2ybts {
            fill:  #34dfa9 !important;
        }
        .st-emotion-cache-b0y9n5.e1d5ycv52:hover {
            color: white !important;
        }
        ::-webkit-scrollbar:focus {
        border: 1px solid #34dfa9 !important;        
        }
                
        .st-ee {
            border-right-color: #34dfa9 !important;  
        }
        .st-eg {
            border-bottom-color: #34dfa9 !important;  
        }
                
        .st-ef {
            border-top-color: #34dfa9 !important;
        }
                
        .st-ef {
            border-bottom-color: #34dfa9 !important;
        }
                
        .st-ed {
              border-left-color:   #34dfa9 !important;
        }
        </style>
    """, unsafe_allow_html=True)


    # Initialize session state for Salesforce auth and uploaded file
    if 'salesforce' not in st.session_state:
        st.session_state.salesforce = None

    if 'filtered_df' not in st.session_state:
        st.session_state.filtered_df = None

    if 'auth_code' not in st.session_state:
        st.session_state.auth_code = None

    # Capture OAuth2 Authorization Code from URL
    query_params = st.experimental_get_query_params()
    auth_code = query_params.get("code", [None])[0]
   

    # Save the auth_code in session_state to avoid losing it on rerun
    if auth_code and st.session_state.auth_code is None:
        st.session_state.auth_code = auth_code

    # ================================
    # Step 1: Salesforce Authentication
    # ================================
    if st.session_state.salesforce is None:
        st.header("🔐 Connect to Salesforce")
        if not st.session_state.auth_code:
            auth_link = f"{AUTH_URL}?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}"

            # This looks like a button but it's actually a styled <a> link
            st.markdown(f"""
                <a href="{auth_link}">
                    <button style="
                        background-color:#34dfa9;
                        color:black;
                        font-weight:bold;
                        border:none;
                        padding:12px 24px;
                        border-radius:8px;
                        cursor:pointer;
                        font-size:16px;
                    ">🔗 Connect to Salesforce</button>
                </a>
            """, unsafe_allow_html=True)
        else:
            sf = get_salesforce_token(st.session_state.auth_code)
            if sf:
                st.session_state.salesforce = sf
                st.rerun()  # Rerun app after successful auth


    # ================================
    # Step 2: File Upload and Processing
    # ================================
    if st.session_state.salesforce:
        st.success("✅ Connected to Salesforce!")

        # File uploader
        uploaded_file = st.file_uploader("📤 Upload CSV File", type=["csv"])

        if uploaded_file is not None:
            try:
                # Read the uploaded file
                file_content = uploaded_file.getvalue()
                if uploaded_file.name.endswith('.csv'):
                    df = pd.read_csv(io.StringIO(file_content.decode('utf-8')), on_bad_lines='skip')
                else:
                    df = pd.read_excel(io.BytesIO(file_content))

                st.success("✅ File Uploaded and Parsed Successfully!")
                st.write("### 🔍 Preview Uploaded Data:")
                st.dataframe(df)

                # Extract and filter job titles
                if 'Job Title' in df.columns:
                    selected_titles, selected_peos = job_title_selector(df)


                    # Filter DataFrame based on selection
                    filtered_df = df[df['Job Title'].isin(selected_titles) & df['PEO (Normalized)'].isin(selected_peos)]
                    st.session_state.filtered_df = filtered_df

                    st.write(f"### ✅ Filtered Data (Showing {len(filtered_df)} of {len(df)} rows):")
                    st.dataframe(filtered_df)


                    # Download filtered data
                    def convert_df_to_csv(df):
                        return df.to_csv(index=False).encode('utf-8')

                    csv_data = convert_df_to_csv(filtered_df)
                    st.download_button(
                        label="📥 Download Filtered Data as CSV",
                        data=csv_data,
                        file_name='filtered_executive_data.csv',
                        mime='text/csv'
                    )

                    # Push to Salesforce
                    selected_object = st.selectbox("📁 Select Salesforce Object to Push Data:", ['Lead'])
                    # Allow user to limit number of leads to send
                    max_leads = len(filtered_df)
                    num_to_push = st.number_input(
                        "🎯 How many leads would you like to push?",
                        min_value=1,
                        max_value=max_leads,
                        value=max_leads,
                        step=1,
                        key="num_to_push"
                    )

                    df_to_push = filtered_df.head(num_to_push)
                    if st.button("🚀 Push Filtered Data to Salesforce"):
                        push_to_salesforce(st.session_state.salesforce, df_to_push, selected_object)
                else:
                    st.error("❌ The uploaded file does not contain a 'Job Title' column.")
            except Exception as e:
                st.error(f"❌ Error processing the uploaded file: {e}")


if __name__ == "__main__":
    main() 
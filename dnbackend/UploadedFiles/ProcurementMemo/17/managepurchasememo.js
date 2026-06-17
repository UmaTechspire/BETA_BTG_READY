import React, { useState, useEffect } from "react";
import { Card, CardBody, Col, Container, Row, Modal,ModalFooter, ModalHeader, ModalBody, Label, FormGroup, Input, InputGroup } from "reactstrap";
import Breadcrumbs from "../../../components/Common/Breadcrumb";
import { classNames } from 'primereact/utils';
import { FilterMatchMode, FilterOperator } from 'primereact/api';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { InputText } from 'primereact/inputtext';
import { IconField } from 'primereact/iconfield';
import { InputIcon } from 'primereact/inputicon';
import { Dropdown } from 'primereact/dropdown';
import { InputNumber } from 'primereact/inputnumber';
import { Button } from 'primereact/button';
import { ProgressBar } from 'primereact/progressbar';
import { Calendar } from 'primereact/calendar';
import { MultiSelect } from 'primereact/multiselect';
import { Slider } from 'primereact/slider';
import { Tag } from 'primereact/tag';
import { TriStateCheckbox } from 'primereact/tristatecheckbox';
import "primereact/resources/themes/lara-light-blue/theme.css";
import { useHistory } from "react-router-dom";
import Flatpickr from "react-flatpickr"
import { AutoComplete } from "primereact/autocomplete";
import Select from "react-select";
import {DeleteMemo, DownloadMemoFileById,GetAllProcurementMemos, GetCommonProcurementUserDetails,ProcurementMemoGetById } from "common/data/mastersapi";
import Swal from 'sweetalert2';
import * as XLSX from "xlsx";
import { saveAs } from "file-saver";

// Move the initFilters function definition above
const initFilters = () => ({
    global: { value: null, matchMode: FilterMatchMode.CONTAINS },
    PM_Number: { operator: FilterOperator.AND, constraints: [{ value: null, matchMode: FilterMatchMode.EQUALS }] },
    PM_Date: { operator: FilterOperator.AND, constraints: [{ value: null, matchMode: FilterMatchMode.STARTS_WITH }] },
    hod: { operator: FilterOperator.AND, constraints: [{ value: null, matchMode: FilterMatchMode.EQUALS }] },
    RequestorName: { operator: FilterOperator.AND, constraints: [{ value: null, matchMode: FilterMatchMode.STARTS_WITH }] },
    ApproveStatus: { operator: FilterOperator.AND, constraints: [{ value: null, matchMode: FilterMatchMode.STARTS_WITH }] },
    Status: { operator: FilterOperator.AND, constraints: [{ value: null, matchMode: FilterMatchMode.STARTS_WITH }] },
});

const FilterTypes = [
    // { name: 'Requestor', value: 1 }
    { name: 'PM NUmber', value: 1 }
];

const getUserDetails = () => {
    if (localStorage.getItem("authUser")) {
        const obj = JSON.parse(localStorage.getItem("authUser"))
        return obj;
    }
}

const ManagePurchaseMemo = () => {
    const history = useHistory();

    const [purchasememo, setpurchasememo] = useState([]);

    const [globalFilterValue, setGlobalFilterValue] = useState("");
    const [filters, setFilters] = useState(initFilters()); // Initialize with the filters
    const [statuses] = useState([
        { label: 'Saved', value: 'Saved' },
        { label: 'Posted', value: 'Posted' },
        // {label: 'Cancelled', value: 'Cancelled'},
         {label: 'Closed', value: 'Closed'}
        // { label: 'New', value: 'new' },
        // { label: 'Negotiation', value: 'negotiation' },
        // { label: 'Renewal', value: 'renewal' },
        // { label: 'Proposal', value: 'proposal' }
    ]);
    const [loading, setLoading] = useState(false);
    const [switchStates, setSwitchStates] = useState({});
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [selectedRow, setSelectedRow] = useState(null);
    const [txtStatus, setTxtStatus] = useState(null);
    const [selectedFilterType, setSelectedFilterType] = useState(null);
    const [selectedAutoItem, setSelectedAutoItem] = useState(null);
    const [autoSuggestions, setAutoSuggestions] = useState([]);
    const [branchId, setBranchId] = useState(1);
    const [orgId, setOrgId] = useState(1);
        const [UserData, setUserData] = useState(null);
    const [detailVisible, setDetailVisible] = useState(false);
        const [selectedDetail, setSelectedDetail] = useState({});
            const [previewUrl, setPreviewUrl] = useState("");
            const [fileName, setFileName] = useState("");
    const getSeverity = (Status) => {
        switch (Status) {
            case 'NotApproved':
                return 'danger';
            case 'Approved':
                return 'success';
            case 'Posted':
                return 'success';
            case 'Saved':
                return 'danger';
            case 'Closed':
                return 'info';
            case 'Cancelled':
                return 'tag-lightred';
            case 'renewal':
                return null;
                case 'Pending':
                    return 'danger';
        }
    };

    const fetchAllProcurementMemos = async (id, orgId, branchId,pmnumber) => {
        const res = await GetAllProcurementMemos(id, orgId, branchId,pmnumber);
        if (res.status) {
            setpurchasememo(res.data)
        } else {
            Swal.fire({
                icon: 'error',
                title: 'Initial Load Failed',
                text: res.message || 'Unable to fetch default claim and payment data.',
            });
        }
    };
    
    useEffect(() => {     
        
        const userData = getUserDetails();
        setUserData(userData);
        console.log("Login data : ", UserData?.u_id);

        fetchAllProcurementMemos(0, orgId, branchId,"%");
    }, []);

    useEffect(() => {
        const customerData = getCustomers();
        const initialSwitchStates = {};
        customerData.forEach(customer => {
            initialSwitchStates[customer.Code] = customer.Active === 1;
        });
        setSwitchStates(initialSwitchStates);
    }, []);

    const [isModalOpen2, setIsModalOpen2] = useState(false);
    const toggleModal2 = () => {
        setIsModalOpen2(!isModalOpen2);
    };


    
        const handleShowDetails = async (row) => {
            const res = await ProcurementMemoGetById(row.Memo_ID, 1, 1);
            if (res.status) {
    
                setSelectedDetail(res.data);
                setDetailVisible(true);
    
                setPreviewUrl(res.data.header.AttachmentPath == undefined || res.data.header.AttachmentPath == null ? "" : res.data.header.AttachmentPath);
                setFileName(res.data.header.AttachmentName == undefined || res.data.header.AttachmentName == null ? "" : res.data.header.AttachmentName);
    
            }
            else {
                Swal.fire("Error", "Data is not available", "error");
    
            }
        };


    const getCustomers = () => {
        return [
            { Code: "SUP000491", Name: "PT HALO HALO BANDUNG", Country: "Indonesia", Contactperson: "Muthu" },
            { Code: "SUP000500", Name: "RAVIKUMAR", Country: "China", Contactperson: "Kevin" },
            { Code: "SUP000492", Name: "SASIKALA", Country: "Indonesia", Contactperson: "Mark" },
            { Code: "SUP000498", Name: "Jane", Country: "Indonesia", Contactperson: "Sophia" },
        ];
    };

    const clearFilter = () => {
        setFilters(initFilters()); // Reset the filters state
        setGlobalFilterValue(''); // Clear the global filter value
    };

    const onGlobalFilterChange = (e) => {
        const value = e.target.value;
        setFilters((prevFilters) => ({
            ...prevFilters,
            global: { ...prevFilters.global, value },
        }));
        setGlobalFilterValue(value);
    };

    const renderHeader = () => {
        return (
            <div className="row align-items-center g-3 clear-spa">
                <div className="col-12 col-lg-3">
                    <Button className="btn btn-danger btn-label" onClick={clearFilter}>
                        <i className="mdi mdi-filter-off label-icon" /> Clear
                    </Button>
                </div>
                <div className="col-12 col-lg-6 text-end">
                    <span className="me-3">
                        <Tag value="S" severity="danger" /> Saved
                    </span>
                    <span className="me-3">
                        <Tag value="P" severity="success" /> Posted
                    </span>
                      <span className="me-3">
                        <Tag value="Clsd" severity="info" /> Closed
                    </span>
                      {/* <span className="me-3">
                        <Tag value="❌" style={{backgroundColor:'white', border:'1px solid red', fontSize: '9px'}} /> Cancelled
                    </span> */}
                    {/* <span className="me-1">
                        <Tag value="Ack" style={{backgroundColor:'#FF7F27',fontSize: '7px'}} /> Acknowledged
                    </span>*/}
                </div>
                <div className="col-12 col-lg-3">
                    <input
                        className="form-control"
                        type="text"
                        value={globalFilterValue}
                        onChange={onGlobalFilterChange}
                        placeholder="Keyword Search"
                    />
                </div>
            </div>
        );
    };
    const actionMemoBodyTemplate = (rowData) => {
        return <span style={{ cursor: "pointer", color: "blue" }} className="btn-rounded btn btn-link"
            onClick={() => handleDownloadFile(rowData)}>{rowData.AttachmentName}</span>;
    };
      const handleDownloadFile = async (data) => {
            const fileId = 0;
          
            var filepath=data.AttachmentPath == undefined || data.AttachmentPath == null ? "" : data.AttachmentPath;
    
            const fileUrl = await DownloadMemoFileById(data.Memo_ID, filepath);
     
        };
    const header = renderHeader();

    const filterClearTemplate = (options) => {
        return <Button type="button" icon="pi pi-times" onClick={options.filterClearCallback} severity="secondary"></Button>;
    };

    const filterApplyTemplate = (options) => {
        return <Button type="button" icon="pi pi-check" onClick={options.filterApplyCallback} severity="success"></Button>;
    };

    const filterFooterTemplate = () => {
        return <div className="px-3 pt-0 pb-3 text-center">Filter by Country</div>;
    };

    const linkAddPurchaseMemo = () => {
        history.push("/procurementsadd-memo");
    };

    const editRow = (rowData) => {
        // console.log('Edit row:', rowData);
        history.push(`/edit-procurements-memo/${rowData.Memo_ID}`);
    };


    const handleDeleteConfirm = (row) => {
        Swal.fire({
          title: 'Are you sure?',
          text: 'Do you want to delete this memo?',
          icon: 'warning',
          showCancelButton: true,
          confirmButtonColor: '#d33',
          cancelButtonColor: '#3085d6',
          confirmButtonText: 'Yes, delete it!',
        }).then((result) => {
          if (result.isConfirmed) {
            deletememo(row);
          }
        });
      };


      const deletememo = async (row) => {
        try {
          const payload = {
            delete: {
              inActiveBy: UserData?.u_id || 0,        // Replace with your actual user ID
              inActiveIP: '127.0.0.1',        // Replace with actual IP if required
              memoId: row.Memo_ID
            }
          };
 
          const response = await DeleteMemo(payload); // Make sure this API is imported
      
          if (response?.status) {
            Swal.fire('Deleted!', 'Memo has been deleted.', 'success');
            searchData(); // Reload the table after delete
          } else {
            Swal.fire('Error', 'Failed to delete the Memo.', 'error');
          }
        } catch (error) {
          Swal.fire('Error', 'An error occurred during deletion.', 'error');
        }
      };

    const actionBodyTemplate = (rowData) => {  
        return (
            <div className="d-flex align-items-center justify-content-center gap-2">
               
                {rowData.Status ==='Saved' ? (
                    <span onClick={() => editRow(rowData)} 
                    title="Edit" style ={{cursor:'pointer'}}>
                    <i className="mdi mdi-square-edit-outline" style={{ fontSize: '1.5rem' }}></i>
                </span>):(
                    <span title ="">
                        <i className="mdi mdi-square-edit-outline"
                        style ={{fontSize : '1.5rem', color:'gray', opacity:0.5}}
                        ></i>
                    </span>
                )}   


                
{ rowData.isSubmitted ==0  ?(

<span onClick={()=> handleDeleteConfirm(rowData)}
style={{     display: 'flex', alignItems: 'center' }}
title="Cancel"
>
<i className="mdi mdi-trash-can-outline" style={{ fontSize: '1.5rem' }}  ></i>
</span>
 
):(
    <span  
style={{  color: "gray",  display: 'flex', alignItems: 'center' }}
title="Cancel"
>
<i className="mdi mdi-trash-can-outline" style={{ fontSize: '1.5rem' }}  ></i>
</span>
)}

                 
                
 
            </div>            
        );
    };

      
    const statusBodyTemplate1 = (data) => {
         return <Tag value={data.ApproveStatus=="Approved" ? "Approved" :"Pending"} severity={getSeverity(data.ApproveStatus)} rounded/>;
    };
     const statusFilterTemplate1 = () => {};

    const statusBodyTemplate = (rowData) => {
        const statusShort = rowData.Status === "Saved" ? "S" : rowData.Status === "Posted" ? "P" : rowData.Status;
        return <Tag value={statusShort} severity={getSeverity(rowData.Status)} />;
    };

    const statusFilterTemplate = (options) => {
        return <Dropdown value={options.value} options={statuses} onChange={(e) => options.filterCallback(e.value, options.index)} itemTemplate={statusItemTemplate} placeholder="Select One" className="p-column-filter" showClear />;
    };

    const statusItemTemplate = (option) => {
        return <Tag value={option.label} severity={getSeverity(option.value)} />;
    };

    const onSwitchChange = () => {
        if (!selectedRow) return;

        const newStatus = !switchStates[selectedRow.Code];
        setSwitchStates(prevStates => ({
            ...prevStates,
            [selectedRow.Code]: newStatus,
        }));

        setCustomers(prevCustomers =>
            prevCustomers.map(customer =>
                customer.Code === selectedRow.Code ? { ...customer, Active: newStatus ? 1 : 0 } : customer
            )
        );
        console.log(`Customer ${selectedRow.Code} Active Status:`, newStatus ? 1 : 0);
        setIsModalOpen(false);
    };

    const openModal = (rowData) => {
        const value = rowData.Active == 1 ? "deactive" : "active";
        setTxtStatus(value);
        setSelectedRow(rowData);
        setIsModalOpen(true);
    };
    const actionBodyTemplate2 = (rowData) => {
        return (
            <div className="square-switch">
                <Input
                    type="checkbox"
                    id={`square-switch-${rowData.Code}`}
                    switch="bool"
                    onChange={() => openModal(rowData)}
                    checked={switchStates[rowData.Code] || false}
                />
                <label htmlFor={`square-switch-${rowData.Code}`} data-on-label="Yes" data-off-label="No" style={{ margin: 0 }} />
            </div>
        );
    };

    const loadSuggestions = async (e) => {
        const query = e.query?.trim() || "%";
        let result = await GetCommonProcurementUserDetails(0,orgId,branchId, query);
        setAutoSuggestions(Array.isArray(result.data) ? result.data : []);
    };

    const searchData = async () => {
        const filterValue = selectedAutoItem?.userid || 0;
        const pmnumber = selectedAutoItem?.pmnumber == undefined || selectedAutoItem?.pmnumber == null ? "%" : selectedAutoItem?.pmnumber;
        fetchAllProcurementMemos(filterValue, orgId, branchId,pmnumber);
    };

    const cancelFilter = async () => {
        setSelectedFilterType(null);
        setSelectedAutoItem(null);
        fetchAllProcurementMemos(0, orgId, branchId,"%");
    };

    const exportToExcel = () => {
        const exportData = purchasememo.map((item) => ({
            // "Memo ID": item.Memo_ID ?? '',
            "PM Number": item.PM_Number ?? '',
            "PM Date": item.PM_Date ?? '',
            "HOD" : item.hod ?? '',
            "PR Approval Status" : item.ApproveStatus ?? '',
            // "Requestor": item.RequestorName ?? '',
            "Status": item.Status ?? '',
        }));

        const worksheet = XLSX.utils.json_to_sheet(exportData);
        const workbook = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(workbook, worksheet, "ProcurementMemos");

        const excelBuffer = XLSX.write(workbook, { bookType: "xlsx", type: "array" });
        const data = new Blob([excelBuffer], {
            type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        });

        const now = new Date();
        const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        const day = String(now.getDate()).padStart(2, "0");
        const month = months[now.getMonth()];
        const year = now.getFullYear();

        let hours = now.getHours();
        const minutes = String(now.getMinutes()).padStart(2, "0");
        const ampm = hours >= 12 ? "pm" : "am";
        hours = hours % 12 || 12;

        const timeStr = `${hours}${minutes}${ampm}`;
        const fileName = `BTG-ProcurementMemos-${day}${month}${year}-${timeStr}.xlsx`;

        saveAs(data, fileName);
    };


    const actionclaimBodyTemplate = (rowData) => {
        return <span style={{ cursor: "pointer", color: "blue" }} className="btn-rounded btn btn-link"
            onClick={() => handleShowDetails(rowData)}>{rowData.PM_Number}</span>;



    };
 // Handle input change
 const handleInputChange = (e) => {
    debugger;
    const { name, value } = e.target;
    setSelectedAutoItem((prevState) => ({
        ...prevState,
        ["pmnumber"]: value, // Update the specific field in state
    }));
};
    return (
        <React.Fragment>
            <div className="page-content">
                <Container fluid>
                    <Breadcrumbs title="Procurement" breadcrumbItem="Purchase Memo" />
                    <Row>
                        <Card className="search-top">
                            <div className="row align-items-end g-1 quotation-mid">
                                <div className="col-12 col-lg-3 mt-1">
                                    <div className="d-flex align-items-center gap-2">
                                        <div className="col-12 col-lg-4 col-md-4 col-sm-4 text-center">
                                            <label htmlFor="Search_Type" className="form-label mb-0">Search By</label></div>
                                        <div className="col-12 col-lg-8 col-md-8 col-sm-8">
                                            <Select
                                                name="filtertype"
                                                options={FilterTypes.map(f => ({ label: f.name, value: f.value }))}
                                                placeholder="Select Filter Type"
                                                classNamePrefix="select"
                                                isClearable
                                                value={selectedFilterType}
                                                onChange={(selected) => {
                                                    setSelectedFilterType(selected);
                                                    setSelectedAutoItem(null);
                                                }}
                                            />
                                        </div>
                                    </div>
                                </div>

                                {selectedFilterType && (
                                    <div className="col-12 col-lg-4 mt-1">
                                        <div className="d-flex align-items-center gap-2">
                                            <div className="col-12 col-lg-4 col-md-4 col-sm-4 text-center">
                                                <label className="form-label mb-0">PM Number</label>
                                            </div>
                                            <div className="col-12 col-lg-8 col-md-8 col-sm-8">
                                                <Input type="text" name="PM" id="PM" value={selectedAutoItem?.pmnumber || ""} onChange={handleInputChange}  ></Input>

                                                
                                                {/* <AutoComplete
                                                    value={selectedAutoItem}
                                                    suggestions={autoSuggestions}
                                                    completeMethod={loadSuggestions}
                                                    field="username"
                                                    onChange={(e) => setSelectedAutoItem(e.value)}
                                                    placeholder={`Search Requestor`}
                                                    style={{ width: "100%" }}
                                                    className={`my-autocomplete`}
                                                /> */}
                                            </div>
                                        </div>
                                    </div>
                                )}


                                {/* Action Buttons */}
                                <div className={`col-12 ${selectedFilterType ? 'col-lg-5' : 'col-lg-9'} d-flex justify-content-end flex-wrap gap-2`} >
                                    <div className="d-flex justify-content-end gap-2 align-items-center h-100">
                                        <button
                                            type="button"
                                            className="btn btn-info"
                                            onClick={searchData}
                                        >
                                            <i className="bx bx-search-alt label-icon font-size-16 align-middle me-2"></i>{" "}
                                            Search
                                        </button>
                                        <button
                                            type="button"
                                            className="btn btn-danger"
                                            onClick={cancelFilter}
                                        >
                                            <i className="bx bx-window-close label-icon font-size-14 align-middle me-2"></i>{" "}
                                            Cancel
                                        </button>
                                        <button
                                            type="button"
                                            className="btn btn-secondary"
                                            onClick={exportToExcel}
                                        >
                                            {" "}
                                            <i className="bx bx-export label-icon font-size-16 align-middle me-2"></i>{" "}
                                            Export
                                        </button>
                                        <button type="button" className="btn btn-success" onClick={linkAddPurchaseMemo}><i className="bx bx-plus label-icon font-size-16 align-middle me-2"></i>New</button>
                                    </div>
                                </div>
                            </div>
                        </Card>
                    </Row>
                    <Row>
                        <Col lg="12">
                            <Card>
                                <DataTable
                                    value={purchasememo}
                                    paginator
                                    showGridlines
                                    rows={10}
                                    loading={loading}
                                    dataKey="Memo_ID"
                                    filters={filters}
                                    globalFilterFields={['PM_Number', 'PM_Date', 'hod','ApproveStatus','RequestorName', 'Status']}
                                    emptyMessage="No procurement memos found."
                                    header={header}
                               
                                 
                                    onFilter={(e) => setFilters(e.filters)}
                                    className="blue-bg"
                                    >

                                           <Column field="PM_Number" sortable style={{ width: '10%' }}  body={actionclaimBodyTemplate} header="PM Number" filter className="text-left" filterPlaceholder="Search by PM_Number" />

                                    {/* <Column
                                        field="PM_Number"
                                        header="PM Number"
                                        filter
                                        filterPlaceholder="Search by Seq No"
                                        className="text-left"
                                        style={{ width: "15%" }}
                                        sortable
                                    /> */}
                                  
                                    
                                    <Column
                                        field="PM_Date"
                                        header="PM Date"
                                        filter
                                        filterPlaceholder="Search by Date"
                                        className="text-center"
                                        sortable
                                        // body={(rowData) => {
                                        // const date = rowData?.PM_Date ? new Date(rowData.PM_Date) : null;
                                        // return date ? date.toLocaleDateString("en-GB") : '';
                                        // }}
                                        
                                        style={{ width: "15%" }}
                                    />
                                    {/* <Column
                                        field="RequestorName"
                                        header="Requestor"
                                        filter
                                        filterPlaceholder="Search by Requestor"
                                        className="text-left"
                                    /> */}

<Column
                                        field="hod"
                                        header="HOD"
                                        filter
                                        filterPlaceholder="Search by HOD"
                                        className="text-left"
                                        style={{ width: "15%" }}
                                        sortable
                                        
                                    />
                                    <Column field="ApproveStatus" header="PR Approval Status" sortable filterMenuStyle={{ width: '14rem' }} body={statusBodyTemplate1} filter filterElement={statusFilterTemplate1} className="text-center" style={{ width: "15%" }}/>
                                    
                                    <Column field="Status" sortable header="Status" filterMenuStyle={{ width: '14rem' }} body={statusBodyTemplate} filter filterElement={statusFilterTemplate} className="text-center" style={{ width: "10%" }}/>
                                    <Column header="Action" showFilterMatchModes={false} body={actionBodyTemplate} className="text-center" style={{ width: "10%" }}/>
                                    </DataTable>
                            </Card>
                        </Col>
                    </Row>
                </Container>
            </div>
            {/* Confirmation Modal */}
            <Modal isOpen={isModalOpen} toggle={() => setIsModalOpen(false)} centered>
                <ModalBody className="py-3 px-5">
                    <Row>
                        <Col lg={12}>
                            <div className="text-center">
                                <i className="mdi mdi-alert-circle-outline" style={{ fontSize: "9em", color: "orange" }} />                                
                                <h4>Do you want to {txtStatus} this account?</h4>
                            </div>
                        </Col>
                    </Row>
                    <Row>
                        <Col>
                            <div className="text-center mt-3 button-items">
                                <Button className="btn btn-info" color="success" size="lg" onClick={onSwitchChange}>
                                    Yes
                                </Button>
                                <Button color="danger" size="lg" className="btn btn-danger" onClick={() => setIsModalOpen(false)}>
                                    Cancel
                                </Button>
                            </div>
                        </Col>
                    </Row>
                </ModalBody>
            </Modal>


            
            <Modal isOpen={detailVisible} toggle={() => setDetailVisible(false)} size="xl">
                <ModalHeader toggle={() => setDetailVisible(false)}>Memo Details</ModalHeader>
                <ModalBody>
                   
                    {1 == 1 && (
                        <>
                            <Row form>
                                {[
                                    ["PM No ", selectedDetail.header?.PM_Number],
                                    ["PM Date", selectedDetail.header?.PMDatec],
                                    ["BTG Delivery Addresst ", selectedDetail.header?.DeliveryAddress],
                                    ["HOD ", selectedDetail.header?.hod],

                                    ["Email Notification", selectedDetail.header?.isEmailNotificationcon],

                                ].map(([label, val], i) => (
                                    <Col md="4" key={i} className="form-group row ">
                                        <Label className="col-sm-4 col-form-label bold">{label}</Label>
                                        <Col sm="8" className="mt-2">: {val}</Col>
                                    </Col>
                                ))}
                            </Row>
                            <hr />
                            <DataTable value={selectedDetail.details}>
                                <Column headerStyle={{ textAlign: 'center' }} header="#" body={(_, { rowIndex }) => rowIndex + 1} />
                                <Column headerStyle={{ textAlign: 'center' }} field="groupname" header="Item Group" />
                                <Column headerStyle={{ textAlign: 'center' }} field="itemname" header="Item Name" />
                                <Column headerStyle={{ textAlign: 'center' }} field="DepartmentName" header="Department" />
                                <Column headerStyle={{ textAlign: 'center' }} field="UOM" header="UOM" />
                                <Column headerStyle={{ textAlign: 'center' }} field="Qty" header="Qty" />
                                <Column headerStyle={{ textAlign: 'center' }} field="AvailStk" header="Avail. Stock" />
                                <Column headerStyle={{ textAlign: 'center' }} field="DeliveryDatecont" header="Del. Date" />
 
                            </DataTable>

                            <Row className="mt-3">
                                <Col>
                                    <Label>Remarks</Label>
                                    <Input type="textarea" rows="2" disabled value={selectedDetail.header?.Remarks} />
                                </Col>
                            </Row>
                            <br/>

                            <DataTable tableStyle={{width:"30%"}} value={selectedDetail.attachment}>
                                <Column headerStyle={{ textAlign: 'center' }} header="#" body={(_, { rowIndex }) => rowIndex + 1} />
                             
                               <Column field="AttachmentName"    body={actionMemoBodyTemplate} header="Attachment"   className="text-left" filterPlaceholder="Search by Attachment" />
                                {/* <Column headerStyle={{ textAlign: 'center' }} field="AttachmentName" header="Attachment Name" /> */}

                            </DataTable>





 
                        </>
                    )}
                </ModalBody>
                <ModalFooter>


                    <button type="button" className="btn btn-danger" onClick={() => setDetailVisible(false)}> <i className="bx bx-export label-icon font-size-16 align-middle me-2"></i> Close</button>

                </ModalFooter>
            </Modal>
        </React.Fragment>
    );
};

export default ManagePurchaseMemo;

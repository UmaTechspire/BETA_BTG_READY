import React, { useState, useEffect } from "react";
import { useHistory, useParams } from "react-router-dom";
import { Button, Col, Card, CardBody, Container, FormGroup, Label, Row, TabContent, TabPane, NavItem, Table, Input, NavLink, InputGroup, UncontrolledAlert } from "reactstrap";
import Breadcrumbs from "../../../components/Common/Breadcrumb";
import classnames from "classnames";
import { Formik, Field, Form, FieldArray } from "formik";
import * as Yup from "yup";
import "flatpickr/dist/themes/material_blue.css"
import Flatpickr from "react-flatpickr"
import { CKEditor } from "@ckeditor/ckeditor5-react";
import ClassicEditor from "@ckeditor/ckeditor5-build-classic";
import { Editor } from "react-draft-wysiwyg";
import "react-draft-wysiwyg/dist/react-draft-wysiwyg.css";
import Swal from 'sweetalert2';
import { DownloadMemoFileById,ProcurementMemouploadFileToServer, GetCommonProcurementItemGroupDetails, GetCommonProcurementDepartmentDetails, GetCommonProcurementItemDetails, GetCommonProcurementPurchaseMemoSeqNo, GetCommonProcurementPurchaseTypeDetails, GetCommonProcurementUomDetails, GetCommonProcurementUserDetails, ProcurementMemoGetById, SaveProcurementMemo } from "common/data/mastersapi";
import { AutoComplete } from "primereact/autocomplete";
import Select from "react-select";
import { Modal, ModalHeader, ModalBody, ModalFooter } from "reactstrap";
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';

const AddPurchaseMemo = () => {
    const { id } = useParams();
    const purchase_memo_id = Number(id ?? 0);
    const isEditMode = !!id;
    const [branchId, setBranchId] = useState(1);
    const [orgId, setOrgId] = useState(1);
    const [userId, setUserId] = useState(1);
    const history = useHistory();
    const [activeTab, setActiveTab] = useState(1);
    const API_URL = process.env.REACT_APP_API_URL;
    const toggleTab = (tab) => {
        if (activeTab !== tab) {
            setActiveTab(tab);
        }
    };
    const [uomOptions, setUomOptions] = useState([]);
    const [pmTypeSuggestions, setPmTypeSuggestions] = useState([]);
    const [selectedPmType, setSelectedPmType] = useState(null);
    const [departmentSuggestions, setDepartmentSuggestions] = useState([]);
    const [itemNameSuggestions, setItemNameSuggestions] = useState({});
    const [requestorSuggestions, setRequestorSuggestions] = useState([]);
    const [selectedRequestor, setSelectedRequestor] = useState(null);

    const [editingRowIndex, setEditingRowIndex] = useState(null);

    const [itemGroupOptions, setItemGroupOptions] = useState([]);
    const [itemNameOptions, setItemNameOptions] = useState({});

    const [attachments, setAttachments] = useState([]);
    const [showAttachmentModal, setShowAttachmentModal] = useState(false);

    const[attachmentdata,setattachmentdata]=useState([]);
    const [initialValues, setInitialValues] = useState({
        pmNo: "",
        pmType: '',
        // pmDate: "",
        pmDate: new Date().toISOString().slice(0, 10),
        requestor: '',
        btgDeliveryAddress: "",
        remarks: "",
        isEmailNotification: 0,
        isNew: 0,

        items: [
            {
                itemName: null,
                department: null,
                uom: "",
                qty: "",
                availableStock: "",
                deliveryDate: "",
            },
        ],
    });

    const handleFileChange = (e) => {
        const files = Array.from(e.target.files);
        setAttachments((prev) => {
            const existing = prev.map(f => f.name + f.lastModified);
            const newFiles = files.filter(
                f => !existing.includes(f.name + f.lastModified)
            );
            return [...prev, ...newFiles];
        });
    };

    const removeAttachment = (index) => {
        setAttachments((prev) => prev.filter((_, i) => i !== index));
    };

    const toggleAttachmentModal = () => setShowAttachmentModal(!showAttachmentModal);

    const loadItemGroupOptions = async () => {
        const res = await GetCommonProcurementItemGroupDetails(purchase_memo_id, orgId, branchId, '%');
        debugger;
        if (res.status) {
            const options = Array.isArray(res.data) ? res.data.map(x => ({
                label: x.groupname,
                value: x.groupid,
            })) : [];

            setItemGroupOptions(options);
        }
    };
    const loadItemNameOptions = async (itemGroupId, index) => {
        debugger;
        const res = await GetCommonProcurementItemDetails(purchase_memo_id, orgId, branchId, "%", itemGroupId);
        const options = Array.isArray(res.data) ? res.data.map(x => ({
            label: x.itemname,
            value: x.itemid,
            stock: x.stock,
            uom:x.uom
        })) : [];

        setItemNameOptions(prev => ({ ...prev, [index]: options }));
    };

    const validationSchema = Yup.object().shape({
        pmNo: Yup.string().required("PM No. is required"),

        //pmType: Yup.number()
        //  .typeError("PM Type is required")
        //.required("PM Type is required"),

        pmDate: Yup.date()
            .required("PM Date is required")
            .typeError("Invalid PM Date"),

        // requestor: Yup.number()
        //     .typeError("Requestor is required")
        //     .required("Requestor is required"),

        btgDeliveryAddress: Yup.string()
            .required("BTG Delivery Address is required"),

       // remarks: Yup.string().required("Remarks are required"),

   
 
    

       items: Yup.array().when([], {
        is: (items) => items?.some(item =>
          item.itemGroupId || item.itemid || item.departmentid || item.qty || item.deliveryDate
        ),
        then: (schema) =>
          schema.of(
            Yup.object().shape({
              itemid: Yup.string()
                .nullable()
                .required("Item Name is required"),
              departmentid: Yup.string()
                .nullable()
                .required("Department is required"),
              itemGroupId: Yup.string()
                .nullable()
                .required("Item Group is required"),
              uom: Yup.string()
                .required("UOM is required"),
              qty: Yup.number()
                .typeError("Qty must be a number")
                .positive("Qty must be greater than 0")
                .required("Qty is required"),
              availableStock: Yup.number()
                .nullable()
                .typeError("Available Stock must be a number"),
              deliveryDate: Yup.date()
                .required("Delivery Date is required")
                .typeError("Invalid date"),
            })
          ),
        otherwise: (schema) => schema, // no validation if no items are entered
      }),
    });

    function formatDateToMySQL(datetime) {
        if (!datetime) return null;
        const date = new Date(datetime);
        const pad = (n) => n.toString().padStart(2, '0');
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
            `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
    }

    const transformToApiPayload = (values, isSubmitted) => {
        debugger
        if(values.isNew=== 1){
            values.items=[];   
        }
        return {
          
            header: {
                memo_ID: purchase_memo_id || 0,
                pM_Type: 1,//values.pmType,
                pM_Number: values.pmNo,
                pmDate: formatDateToMySQL(values.pmDate),
                requestorId: 0,//values.requestor,
                deliveryAddress: values.btgDeliveryAddress,
                remarks: values.remarks,
                userId: userId,
                isSubmitted: isSubmitted,
                orgId: orgId,
                branchId: branchId,
                isEmailNotification: values.isEmailNotification || 0,
                isNew:values.isNew || 0,
                
                hod: values.hod,  // store in form values
                hodid: values.hodid,       // store hidden id
            },
         
            details: values.items.map((item) => ({
                memo_dtl_ID: item.memoDtlId || 0,
                memo_ID: purchase_memo_id || 0,
                itemId: item.itemid,
                departmentId: item.departmentid,
                itemGroupId: item.itemGroupId,
                uomId: item.uom==null || item.uom==undefined || item.uom=="" ? 0 : item.uom,
                qty: item.qty==null || item.qty==undefined || item.qty=="" ? 0 : item.qty ,
                availStk: item.availableStock === "" ? 0 : parseFloat(item.availableStock),
                deliveryDate: formatDateToMySQL(item.deliveryDate),
                remarks: values.remarks ?? "PM-Memo-Remark",
            }))
        };
    };

    const handleSelect = () => { };

    const handleSubmit = async (values, isSubmitted) => {

debugger;

        const detailsCount = values.items?.filter(row =>
            row.itemGroupId==null || row.itemGroupId==undefined || row.itemGroupId=="" || row.itemGroupId==0  
            || row.itemid==null || row.itemid==undefined || row.itemid=="" || row.itemid==0  
          || row.departmentid==null || row.departmentid==undefined || row.departmentid=="" || row.departmentid==0  
          ||  row.qty==null || row.qty==undefined || row.qty=="" || row.qty==0  
          || row.deliveryDate==null || row.deliveryDate==undefined || row.deliveryDate=="" 
           
        ).length || 0;
    
        const hasRemarks = values.remarks?.trim().length > 0;
        var totalAttachmentsCount = attachments.length; // includes both existing and new
        totalAttachmentsCount +=attachmentdata?.length;
        // Validation rules


        if (values.isNew==1){

            if (!hasRemarks) {
                Swal.fire({
                    icon: 'error',
                    title: 'Remarks Required',
                    text: 'Please enter the remarks.'
                });
                return;
            }

            if (hasRemarks && totalAttachmentsCount === 0) {
                Swal.fire({
                    icon: 'error',
                    title: 'Attachment Required',
                    text: 'Attachments are required when remarks are entered.'
                });
                return;
            }
        
            if (totalAttachmentsCount > 0 && !hasRemarks) {
                Swal.fire({
                    icon: 'error',
                    title: 'Remarks Required',
                    text: 'Remarks are required when attachments are added.'
                });
                return;
            }

        }
        else{

            if ( detailsCount > 0) {
                Swal.fire({
                    icon: 'error',
                    title: 'Missing Data',
                    text: 'Please add memo details.'
                });
                return;
            }

        }
        
    
     

 
        let actionType = 'Save';

        if (isEditMode && !isSubmitted) {
            actionType = 'Update';
        } else if (isSubmitted) {
            actionType = 'Post';
        }

        const result = await Swal.fire({
            title: `Are you sure you want to ${actionType}?`,
            text: `This will ${actionType.toLowerCase()} the procurement memo.`,
            icon: 'question',
            showCancelButton: true,
            confirmButtonText: `Yes, ${actionType}`,
            cancelButtonText: 'Close',
        });

        if (!result.isConfirmed) return;

        const payload = transformToApiPayload(values, isSubmitted);

        try {

            const res = await SaveProcurementMemo(isEditMode, payload);

            if (res?.status === true) {
               
               
             
 debugger;
                if (attachments.length > 0) {
                    const uploadFormData = new FormData();
                    attachments.forEach(file => {
                        uploadFormData.append("Attachments", file);
                    });
                    const MemoId = res?.data;
                    // Assuming your upload method is an API call:
                    await ProcurementMemouploadFileToServer( uploadFormData, MemoId, 1,   1);

                    console.log("Attachments uploaded successfully");
                }
                await Swal.fire({
                    icon: 'success',
                    title: 'Success',
                    text: `Procurement memo ${actionType.toLowerCase()}d successfully.`,
                });
                history.push('/procurementspurchase-memo');

            } else {
                Swal.fire({
                    icon: 'error',
                    title: 'Error',
                    text: res?.message || 'Something went wrong while saving the memo.',
                });
            }

        } catch (err) {
            console.error("Save Error:", err);
            Swal.fire({
                icon: 'error',
                title: 'Exception',
                text: 'An unexpected error occurred while saving.',
            });
        }
    };

    const [supplierAddresses, setsupplierAddresses] = useState([
        { code: "CA001", name: "Sara", type: "Billing", suppliername: "Juli", address: "Test address" },
    ]);

    const [productpriceList, setProductpriceList] = useState([
        { GasCode: "CA001", Price: "10", Currency: "USD", FromDate: "20-JAN-2025", EndDate: "20-JAN-2026" },
    ]);

    const [customeraddressDetails, setCustomeraddressDetails] = useState([
        { code: "CA001", name: "Sara", scode: "SPA001", address: "Test Address" },
    ]);

    const loadUomDetails = async () => {
        const res = await GetCommonProcurementUomDetails(purchase_memo_id, orgId, branchId, '%');
        if (Array.isArray(res.data)) {
            const options = (res.data || []).map(uom => ({
                label: uom?.UOMName || "",
                value: uom?.uomid || "",
            }));
            setUomOptions(options);
        } else {
            setUomOptions([]);
        }
    };

    useEffect(() => {
        loadItemGroupOptions();
        loadDepartmentSuggestions();
        const fetchSeqNum = async () => {
            const res = await GetCommonProcurementPurchaseMemoSeqNo(orgId, branchId);
            if (res.status) {
                const data = res.data;
                setInitialValues((prev) => ({
                    ...prev,
                    pmNo: data.MemoNo,
                    hod: data.hod,  // store in form values
                    hodid: data.hodid,       // store hidden id

                }));
            } else {
                Swal.fire({
                    icon: 'error',
                    title: 'Failed to Load Sequence Number',
                    text: res.message || 'Could not fetch Claim and Payment Seq No.',
                });
            }
        };
        if (!isEditMode) {
            fetchSeqNum();
            setEditingRowIndex(0);
        }
        loadUomDetails();
    }, []);




    const actionMemoBodyTemplate = (rowData) => {
        return <span style={{ cursor: "pointer", color: "blue" }} className="btn-rounded btn btn-link"
            onClick={() => handleDownloadFile(rowData)}>{rowData.AttachmentName}</span>;
    };
      const handleDownloadFile = async (data) => {
            const fileId = 0;
          
            var filepath=data.AttachmentPath == undefined || data.AttachmentPath == null ? "" : data.AttachmentPath;
    
            const fileUrl = await DownloadMemoFileById(data.Memo_ID, filepath);
     
        };

    const mapMemoResponseToFormik = (data) => {
        debugger
        const header = data?.header || {};
        const details = data?.details || [];
        const attachment = data?.attachment || [];
        setattachmentdata(attachment);
        return {
            pmNo: header.PM_Number || "",
            pmType: header.PM_Type || "",
            pmDate: header.PMDate?.slice(0, 10) ?? "", 
            requestor: header.RequestorId || "",
            btgDeliveryAddress: header.DeliveryAddress || "",
            remarks: header.Remarks || "",
            // itemGroupId
            // itemid
            // departmentid
       
            
         
            hod: header.hod,  // store in form values
            hodid: header.hodid,       // store hidden id

            isEmailNotification: header.isEmailNotification || 0, // <-- added
            isNew:header.isNew || 0,
            items: details.length > 0
                ? details.map((item) => ({
                    itemname:item.itemname,
                    uom: item.UOMId || "",
                    qty: item.Qty || "",
                    availableStock: item.AvailStk || "",
                    deliveryDate: item.DeliveryDate || "",
                    itemid: item.itemid,
                    itemGroupId: item.itemGroupId,
                    departmentid: item.departmentid,
                    memoDtlId:item.memoDtlId
                  
                }))
                : [
                    {
                        memoDtlId:0,
                        itemid: 0,
                        itemGroupId: 0,
                        departmentid: 0,
                        itemname: null,
                        department: null,
                        uom: "",
                        qty: "",
                        availableStock: "",
                        deliveryDate: "",
                    },
                ],
        };
    };

    const getProcurementMemoGetById = async (memoId) => {
        debugger
        try {
            const res = await ProcurementMemoGetById(memoId, orgId, branchId);
            const header = res.data?.header;
            const formikFormatted = mapMemoResponseToFormik(res.data);
            setInitialValues(formikFormatted);
            setSelectedPmType({
                typename: header.typename,
                typeid: header.PM_Type,
            });

            setSelectedRequestor({
                username: header.RequestorName,
                userid: header.RequestorId,
            });

        } catch (err) {
            Swal.fire("Error", err.message, "error");
        }
    };

    useEffect(() => {
        if (isEditMode) {
            debugger
            getProcurementMemoGetById(purchase_memo_id);
        }
    }, [isEditMode, purchase_memo_id]);

    const handleRemoveItem = (index) => {
        const updatedDetails = supplierAddresses.filter((_, i) => i !== index);
        setsupplierAddresses(updatedDetails);
    };
    const handleCancel = () => {
        history.push("/procurementspurchase-memo");
    };

    const loadPmTypeSuggestions = async (e) => {
        const searchText = e.query;
        const res = await GetCommonProcurementPurchaseTypeDetails(purchase_memo_id, orgId, branchId, searchText);
        setPmTypeSuggestions(Array.isArray(res.data) ? res.data : []);
    };

    const loadRequestorSuggestions = async (e) => {
        const searchText = e.query;
        const res = await GetCommonProcurementUserDetails(purchase_memo_id, orgId, branchId, searchText);
        setRequestorSuggestions(Array.isArray(res.data) ? res.data : []);
    };

    const loadDepartmentSuggestions = async (e) => {

        try {
            const res = await GetCommonProcurementDepartmentDetails(purchase_memo_id, orgId, branchId, "%");

            const options = Array.isArray(res.data) ? res.data.map(x => ({
                label: x.departmentname,
                value: x.departmentid,
            })) : [];


            setDepartmentSuggestions(options);
        } catch (error) {
            console.error("Failed to load department suggestions", error);
            setDepartmentSuggestions(prev => ({ ...prev, [index]: [] }));
        }
    };

    const loadItemNameSuggestions = async (e, index) => {
        const searchText = e.query;

        try {
            const res = await GetCommonProcurementItemDetails(purchase_memo_id, orgId, branchId, searchText);
            setItemNameSuggestions(prev => ({
                ...prev,
                [index]: Array.isArray(res.data) ? res.data : []
            }));
        } catch (error) {
            console.error("Failed to load item name suggestions", error);
            setItemNameSuggestions(prev => ({ ...prev, [index]: [] }));
        }
    };

    const markAllTouched = (obj) => {
        if (Array.isArray(obj)) {
            return obj.map((item) => markAllTouched(item));
        } else if (typeof obj === 'object' && obj !== null) {
            const touchedObj = {};
            for (const key in obj) {
                touchedObj[key] = markAllTouched(obj[key]);
            }
            return touchedObj;
        }
        return true;
    };


    return (

        <React.Fragment>
            <div className="page-content">
                <Container fluid>
                    <Breadcrumbs title="Procurement" breadcrumbItem="Purchase Memo" />
                    <Row>
                        <Col lg="12">
                            <Card>
                                <CardBody>
                                    <Formik enableReinitialize initialValues={initialValues} validationSchema={validationSchema} >
                                        {({ values, errors, touched, setFieldValue, setTouched, validateForm, setFieldTouched }) => (
                                            <Form>
                                                <div className="row align-items-center g-3 justify-content-end">
                                                    <div className="col-12 col-lg-8 col-md-8 col-sm-8">
                                                        {Object.keys(errors).length > 0 && (
                                                            <div className="alert alert-danger alert-new">
                                                                <ul className="mb-0">
                                                                    {(() => {
                                                                        // 1. First check top-level errors
                                                                        for (const [key, value] of Object.entries(errors)) {
                                                                            if (key !== "items") {
                                                                                return <li>{value}</li>;
                                                                            }

                                                                            // 2. Then check nested items array errors
                                                                            if (Array.isArray(value)) {
                                                                                for (let i = 0; i < value.length; i++) {
                                                                                    const itemError = value[i];
                                                                                    if (itemError && typeof itemError === "object") {
                                                                                        const [fieldKey, message] = Object.entries(itemError)[0] || [];
                                                                                        return (
                                                                                            <li>
                                                                                                <strong>Row {i + 1} : </strong> {message}
                                                                                            </li>
                                                                                        );
                                                                                    }
                                                                                }
                                                                            }
                                                                        }

                                                                        return null;
                                                                    })()}
                                                                </ul>
                                                            </div>
                                                        )}
                                                    </div>
                                                    <div className="col-12 col-lg-4 col-md-4 col-sm-4 button-items">
                                                        <button type="button" className="btn btn-danger fa-pull-right" onClick={handleCancel}>
                                                            <i className="bx bx-window-close label-icon font-size-14 align-middle me-2"></i>Close</button>
                                                        <button
                                                            type="button"
                                                            className="btn btn-success fa-pull-right"
                                                            onClick={async () => {
                                                                setTouched(markAllTouched(values), true);
                                                                const validationErrors = await validateForm();

                                                                if (Object.keys(validationErrors).length === 0) {
                                                                    handleSubmit(values, 1); // Post
                                                                }
                                                            }}
                                                        >
                                                            <i className="bx bxs-save label-icon font-size-16 align-middle me-2"></i>Post
                                                        </button>

                                                        <button
                                                            type="button"
                                                            className="btn btn-info fa-pull-right"
                                                            onClick={async () => {
                                                                setTouched(markAllTouched(values), true);
                                                                const validationErrors = await validateForm();

                                                                if (Object.keys(validationErrors).length === 0) {
                                                                    handleSubmit( values, 0); // Save
                                                                }
                                                            }}
                                                        >
                                                            <i className="bx bx-comment-check label-icon font-size-16 align-middle me-2" ></i>{isEditMode ? "Update" : "Save"}
                                                        </button>
                                                    </div>
                                                </div>
                                                <Row className="mb-3">
                                                    <Col md="2">
                                                        <FormGroup>
                                                            <Label htmlFor="pmNo">PM No. <span className="text-danger">*</span></Label>
                                                            <Field
                                                                name="pmNo"
                                                                placeholder="PM No"
                                                                type="text"
                                                                className={`form-control ${errors.pmNo && touched.pmNo ? "is-invalid" : ""}`}
                                                                disabled
                                                            />
                                                            {/* <ErrorMessage name="prNo" component="div" className="invalid-feedback" /> */}
                                                        </FormGroup>
                                                    </Col>
                                                    {/*<Col md={4}>
                                                        <FormGroup>
                                                            <Label htmlFor="pmType" className="fw-bold">
                                                                PM Type. <span className="text-danger">*</span>
                                                            </Label>
                                                            <AutoComplete
                                                                value={selectedPmType}
                                                                suggestions={pmTypeSuggestions}
                                                                completeMethod={loadPmTypeSuggestions}
                                                                field="typename"
                                                                onChange={(e) => {
                                                                    setSelectedPmType(e.value);
                                                                    setFieldValue("pmType", e.value?.typeid); // store ID in form
                                                                }}
                                                                onBlur={() => setFieldTouched("pmType", true)}
                                                                placeholder="Search PM Type"
                                                                style={{ width: '100%' }}
                                                                className="my-autocomplete"
                                                            />
                                                        </FormGroup>
                                                    </Col> */}

                                                    {/* Row 2 */}
                                                    <Col md="2">
                                                        <FormGroup>
                                                            <Label htmlFor="pmDate">PM Date <span className="text-danger">*</span></Label>
                                                            {/* <Field name="pmDate">
                                                                {({ field, form }) => (
                                                                    <Flatpickr
                                                                        {...field}
                                                                        options={{
                                                                            altInput: true,
                                                                            altFormat: "d-M-Y",
                                                                            dateFormat: "Y-m-d",
                                                                        }}
                                                                        className={`form-control`}
                                                                        onChange={date => form.setFieldValue("pmDate", date[0])}
                                                                    />
                                                                )}
                                                            </Field> */}
                                                    <Field name="pmDate" type="date" className="form-control" disabled />
                                                            
                                                        </FormGroup>

                                                    </Col>

                                                    {/* Row 3 
                                                    <Col md="4">
                                                        <FormGroup>
                                                            <Label htmlFor="requestor">Requestor <span className="text-danger">*</span></Label>
                                                            <AutoComplete
                                                                value={selectedRequestor}
                                                                suggestions={requestorSuggestions}
                                                                completeMethod={loadRequestorSuggestions}
                                                                field="username"
                                                                onChange={(e) => {
                                                                    setSelectedRequestor(e.value);
                                                                    setFieldValue("requestor", e.value?.userid);
                                                                }}
                                                                onBlur={() => setFieldTouched("requestor", true)}
                                                                placeholder="Search Requestor"
                                                                style={{ width: '100%' }}
                                                                className="my-autocomplete"
                                                            />
                                                            <ErrorMessage name="requestor" component="div" className="invalid-feedback" />
                                                        </FormGroup>
                                                    </Col>*/}

                                                    <Col md="3">
                                                        <FormGroup>
                                                            <Label htmlFor="btgDeliveryAddress">BTG  Delivery Address <span className="text-danger">*</span></Label>
                                                            <Field
                                                                name="btgDeliveryAddress"
                                                                placeholder="Delivery Address"
                                                                type="text"
                                                                className={`form-control`}
                                                            />
                                                            {/* <ErrorMessage name="deliveryAddress" component="div" className="invalid-feedback" /> */}
                                                        </FormGroup>
                                                    </Col>

                                                    <Col md="2">
                                                        <FormGroup>
                                                            <Label htmlFor="hodName">HOD</Label>
                                                            <div className="d-flex align-items-center justify-content-end gap-2">
                                                                <Field
                                                                    name="hod"
                                                                    placeholder="HOD Name"
                                                                    type="text"
                                                                    className={`form-control`}
                                                                    disabled
                                                                />

                                                            </div>

                                                            {/* <ErrorMessage name="hodApproval" component="div" className="invalid-feedback" /> */}
                                                        </FormGroup>
                                                    </Col>

                                                    <Col md="2" className="d-flex align-items-end">
                                                        <FormGroup>

                                                            <div className="d-flex align-items-end gap-2">
                                                                <input
                                                                    type="checkbox"
                                                                    checked={values.isEmailNotification === 1}
                                                                    onChange={(e) => setFieldValue("isEmailNotification", e.target.checked ? 1 : 0)}
                                                                    style={{ width: '25px', height: '25px', cursor: 'pointer', marginBottom: 5 }}
                                                                />
                                                                <Label htmlFor="hodApproval" style={{ marginBottom: 6 }}>Email Notification</Label>
                                                            </div>

                                                            {/* <ErrorMessage name="hodApproval" component="div" className="invalid-feedback" /> */}
                                                        </FormGroup>
                                                    </Col>

                                                    <Col md="3" className="d-flex align-items-end">
                                                    <FormGroup>
                                                    <div className="form-check" style={{paddingLeft:"0px"}}>
  <input
    type="checkbox"
    className="form-check-input"
    id="isNew"
    name="isNew"
    checked={values.isNew=== 1}
    onChange={(e) => { setAttachments([]); values.remarks=""; values.items=[]; setFieldValue("isNew", e.target.checked ? 1 : 0);}}
  />
  <label className="form-check-label" htmlFor="isNew" style={{color:"firebrick"}}>Is New Item</label>
</div>
</FormGroup>
</Col>

                                                    {/* Row 4 */}
                                                    {/* <Col md="4">
                                                        <FormGroup>
                                                            <Label htmlFor="department">Department</Label>
                                                            <Field as="select" name="department" className="form-select">
                                                                <option value="">Select Department</option>
                                                                <option value="purchase">Purchase</option>
                                                                <option value="sales">Sales</option>
                                                                <option value="finance">Finance</option>
                                                            </Field>
                                                            <ErrorMessage name="department" component="div" className="invalid-feedback" />
                                                        </FormGroup>
                                                    </Col> */}




                                                    {/* <div className="col-xl-12">
                                                        <Col md="12">
                                                            <FormGroup>
                                                                <Label for="remarks">Remarks <span className="text-danger">*</span></Label>
                                                                <Field as="textarea" name="remarks" rows={3} className="form-control" />
                                                            </FormGroup>
                                                        </Col>
                                                    </div> */}
                                                </Row>
                                                
                                                <div style={{ overflowX: "auto" }}>
                                                <Table className="ProcurementTable" style={{ minWidth: "1600px" }}>
                                                    <thead style={{ backgroundColor: "#3e90e2" }}>
                                                        <tr>
                                                            <th className="text-center" style={{ width: "4%" }}>S.No.</th>
                                                            <th className="text-center" style={{ width: "15%" }}>Item Group</th>
                                                            <th className="text-center" style={{ width: "15%" }}>Item Name</th>
                                                            <th className="text-center" style={{ width: "15%" }}>Department</th>
                                                            <th className="text-center" style={{ width: "10%" }}>UOM</th>
                                                            <th className="text-center" style={{ width: "10%" }}>Qty</th>
                                                            <th className="text-center" style={{ width: "10%" }}>Avail. Stock</th>
                                                            <th className="text-center" style={{ width: "10%" }}>Del. Date</th>
                                                            <th className="text-center" style={{ width: "5%" }}>Action</th>

                                                        </tr>
                                                    </thead>
                                                    <FieldArray name="items">
                                                        {({ push, remove }) => (
                                                            <>
                                                                <tbody>
                                                                    {!values.isNew && values.items.map((item, i) => (
                                                                        <tr key={i}>
                                                                            <td className="text-center align-middle">{i + 1}</td>
                                                                            {/* Item Group */}
                                                                            <td>
                                                                                <Select
                                                                                    isDisabled={editingRowIndex !== i}
                                                                                    value={itemGroupOptions?.find(opt => opt.value === item.itemGroupId) || null}

                                                                                    onChange={(selected) => {
                                                                                        setFieldValue(`items[${i}].itemGroupId`, selected?.value || "");
                                                                                        setFieldValue(`items[${i}].itemid`, null);
                                                                                        setFieldValue(`items[${i}].availableStock`, "");
                                                                                        setFieldValue(`items[${i}].uom`,  null);
                                                                                        if (selected?.value) {
                                                                                            loadItemNameOptions(selected.value, i);
                                                                                        }
                                                                                    }}
                                                                                    options={itemGroupOptions || []}
                                                                                    placeholder="Select Item Group"
                                                                                    classNamePrefix="react-select"
                                                                                    menuPortalTarget={document.body}
                                                                                />
                                                                                {errors.items?.[i]?.itemGroupId && touched.items?.[i]?.itemGroupId && (
                                                                                    <div className="text-danger small">{errors.items[i].itemGroupId}</div>
                                                                                )}
                                                                            </td>

                                                                            {/* Item Name */}
                                                                            <td>

                                                                    {editingRowIndex !== i ? (
                                                                                                <Input type="text" disabled={true} value={item.itemname} />
                                                                                  
                                                                                            ) : (
                                                                            
                                                                                <Select

                                                                                    value={itemNameOptions[i]?.find(opt => opt.value === item.itemid) || null}
                                                                                    onChange={(selected) => {
                                                                                        setFieldValue(`items[${i}].itemid`, selected.value || null);
                                                                                        setFieldValue(`items[${i}].uom`, selected.uom || null);
                                                                                        setFieldValue(`items[${i}].itemname`, selected.label || null);
                                                                                        setFieldValue(`items[${i}].availableStock`, selected?.stock || "");
                                                                                    }}
                                                                                    options={itemNameOptions[i] || []}
                                                                                    placeholder="Select Item Name"
                                                                                    classNamePrefix="react-select"
                                                                                    isDisabled={editingRowIndex !== i && !values.items[i].itemGroupId}
                                                                                    menuPortalTarget={document.body}
                                                                                />
                                                                            )}
                                                                                {errors.items?.[i]?.itemid && touched.items?.[i]?.itemid && (
                                                                                    <div className="text-danger small">{errors.items[i].itemid}</div>
                                                                                )}
                                                                           
                                                                            </td>

                                                                            {/* Department */}
                                                                            <td>

                                                                                <Select
                                                                                    isDisabled={editingRowIndex !== i}
                                                                                    value={departmentSuggestions?.find(opt => opt.value === item.departmentid) || null}
                                                                                    onChange={(selected) => {
                                                                                        setFieldValue(`items[${i}].departmentid`, selected.value || null);

                                                                                    }}
                                                                                    options={departmentSuggestions || []}
                                                                                    placeholder="Select Department"
                                                                                    classNamePrefix="react-select"
                                                                                    menuPortalTarget={document.body}
                                                                                />
                                                                                {/* <AutoComplete
                                                                                    value={item.department || null}
                                                                                    suggestions={departmentSuggestions[i] || []}
                                                                                    completeMethod={(e) => loadDepartmentSuggestions(e, i)}
                                                                                    field="departmentname"
                                                                                    onChange={(e) => setFieldValue(`items[${i}].department`, e.value)}
                                                                                    placeholder="Department"
                                                                                    style={{ width: '100%' }}
                                                                                    className="my-autocomplete"
                                                                                /> */}
                                                                                {errors.items?.[i]?.departmentid && touched.items?.[i]?.departmentid && (
                                                                                    <div className="text-danger small">{errors.items[i].departmentid}</div>
                                                                                )}
                                                                            </td>

                                                                            {/* UOM */}
                                                                            <td>
                                                                                <Select
                                                                                    isDisabled={true}
                                                                                  
                                                                                    value={uomOptions.find(opt => opt.value === item.uom) || null}
                                                                                    onChange={(selected) => setFieldValue(`items[${i}].uom`, selected?.value || "")}
                                                                                    options={uomOptions}
                                                                                    placeholder="Select UOM"
                                                                                    classNamePrefix="react-select"
                                                                                    menuPortalTarget={document.body}
                                                                                />
                                                                                {errors.items?.[i]?.uom && touched.items?.[i]?.uom && (
                                                                                    <div className="text-danger small">{errors.items[i].uom}</div>
                                                                                )}
                                                                            </td>

                                                                            {/* Qty */}
                                                                            <td>
                                                                                <Field
                                                                                    disabled={editingRowIndex !== i}
                                                                                    name={`items[${i}].qty`}
                                                                                    type="number"
                                                                                    className="form-control text-end"
                                                                                />
                                                                                {errors.items?.[i]?.qty && touched.items?.[i]?.qty && (
                                                                                    <div className="text-danger small">{errors.items[i].qty}</div>
                                                                                )}
                                                                            </td>

                                                                            {/* Available Stock */}
                                                                            <td>
                                                                                <Field
                                                                                   
                                                                                    name={`items[${i}].availableStock`}
                                                                                    type="number"
                                                                                    className="form-control text-end"
                                                                                    disabled
                                                                                />
                                                                                {errors.items?.[i]?.availableStock && touched.items?.[i]?.availableStock && (
                                                                                    <div className="text-danger small">{errors.items[i].availableStock}</div>
                                                                                )}
                                                                            </td>

                                                                            {/* Delivery Date */}
                                                                            <td>
                                                                                <Flatpickr
                                                                                     
                                                                                    name={`items[${i}].deliveryDate`}
                                                                                    className="form-control"
                                                                                    value={item.deliveryDate}
                                                                                    onChange={(date) =>
                                                                                        setFieldValue(`items[${i}].deliveryDate`, date?.[0] || "")
                                                                                    }
                                                                                    options={{
                                                                                        altInput: true,
                                                                                        altFormat: "d-M-Y",
                                                                                        dateFormat: "Y-m-d",
                                                                                        minDate: "today",
                                                                                        clickOpens: editingRowIndex === i
                                                                                    }}
                                                                                />
                                                                                {errors.items?.[i]?.deliveryDate && touched.items?.[i]?.deliveryDate && (
                                                                                    <div className="text-danger small">{errors.items[i].deliveryDate}</div>
                                                                                )}
                                                                            </td>

                                                                            {/* Remove Button */}
                                                                            <td className="text-center">
                                                                                {/* {i > 0 && ( */}

                                                                                {editingRowIndex === i ? (
                                                                                    <button
                                                                                        type="button"
                                                                                        
                                                                                        onClick={() => setEditingRowIndex(null)}
                                                                                        style={{ background: 'none', border: 'none', padding: 0, marginRight: '10px' }}
                                                                                        >
                                                                                             <i
                                                                                            className="mdi mdi-check text-primary"
                                                                                            style={{ fontSize: '18px', cursor: 'pointer' }}
                                                                                        ></i>
                                                                                           
                                                                                    </button>
                                                                                ) : (
                                                                                    <button
                                                                                        type="button"
                                                                                      
                                                                                        onClick={() =>{  if (item?.itemGroupId ) { loadItemNameOptions(item.itemGroupId, i);}setEditingRowIndex(i);}}
                                                                                        disabled={editingRowIndex !== null}
                                                                                        style={{ background: 'none', border: 'none', padding: 0, marginRight: '10px' }}
                                                                                    >
                                                                                        <i className="mdi mdi-pencil-outline text-success" style={{ fontSize: '18px', cursor: 'pointer' }}></i>
                                                                                    </button>
                                                                                )}

                                                                                <button
                                                                                    type="button"
                                                                                    className="btn btn-sm btn-danger"
                                                                                    onClick={() => remove(i)}
                                                                                    title="Remove Row"
                                                                                    style={{ background: 'none', border: 'none', padding: 0 }}
                                                                                >
                                                                                    <i
                                                                                        className="mdi mdi-delete-outline text-danger"
                                                                                        style={{ fontSize: '18px', cursor: 'pointer' }}
                                                                                    ></i>
                                                                                </button>

                                                                                
                                                                                {/* )} */}
                                                                            </td>


                                                                        </tr>
                                                                    ))}
                                                                </tbody>

                                                                {/* Add Row Button */}
                                                                <tfoot>
                                                                    <tr>
                                                                        {/* Add Row Button across first 4 columns */}
                                                                        <td colSpan="4">
                                                                            <button
                                                                                type="button"
                                                                                className="btn btn-sm"
                                                                                style={{ borderColor: "black", color: "black" }}
                                                                                disabled={values.isNew}
                                                                                onClick={() =>{
                                                                              

                                                                                    setEditingRowIndex(values.items.length);
                                                                                    push({
                                                                                        itemName: null,
                                                                                        department: null,
                                                                                        uom: "",
                                                                                        qty: "",
                                                                                        availableStock: "",
                                                                                        deliveryDate: "",
                                                                                    });
                                                                                }
                                                                                }
                                                                            >+
                                                                            </button>
                                                                        </td>

                                                                        {/* Total Qty Label in 5th column (Qty column) */}
                                                                        <td className="text-end align-middle">
                                                                            <strong>Total Qty</strong>
                                                                        </td>

                                                                        {/* Qty Sum in 6th column */}
                                                                        <td className="text-end align-middle">
                                                                            <strong>
                                                                                {
                                                                                    values.items.reduce((sum, item) => {
                                                                                        const qty = parseFloat(item.qty);
                                                                                        return sum + (isNaN(qty) ? 0 : qty);
                                                                                    }, 0)
                                                                                        .toFixed(2)
                                                                                }
                                                                            </strong>
                                                                        </td>

                                                                        {/* Blank cell for Delivery Date */}
                                                                        <td></td>

                                                                        {/* Blank cell for Delete Icon */}
                                                                        <td></td>
                                                                        <td></td>
                                                                    </tr>
                                                                </tfoot>
                                                            </>
                                                        )}
                                                    </FieldArray>
                                                </Table>
                                                </div>
                                                <div className="col-xl-12 mt-lg-4">
                                                    <Col md="12">
                                                        <FormGroup>
                                                            <Label for="remarks">Remarks </Label>
                                                            <Field as="textarea" disabled={!values.isNew}    checked={values.isNew=== 1} name="remarks" rows={3} className="form-control" />
                                                        </FormGroup>
                                                    </Col>
                                                </div>
                                                <div className="col-xl-12 mt-lg-4">
                                                    <Col md="12">
                                                    <div className="d-flex align-items-end gap-2">
                                                        <Label for="remarks"  >Attachment  </Label>
                                                        <button disabled={!values.isNew} type="button" className="btn btn-success " onClick={toggleAttachmentModal}>
                                                            <i className="fa fa-paperclip label-icon font-size-14 align-middle me-2"></i>Add</button>

</div>
                                                    </Col>
                                                </div>
                                            </Form>
                                        )}
                                    </Formik>
                                </CardBody>
                            </Card>
                        </Col>
                    </Row>
                </Container>
            </div>
            <Modal isOpen={showAttachmentModal} toggle={toggleAttachmentModal}>
                <ModalHeader toggle={toggleAttachmentModal}>Upload Attachments</ModalHeader>
                <ModalBody>
                    <input
                        type="file"
                        multiple
                        onChange={handleFileChange}
                        className="form-control mb-3"
                    />
                    {attachments.length > 0 && (
                        <ul className="list-group">
                            {attachments.map((file, index) => (
                                <li key={index} className="list-group-item d-flex justify-content-between align-items-center">
                                    {file.name}

                                    <span onClick={()=> removeAttachment(index)}
style={{     display: 'flex', alignItems: 'center' }}
title="Cancel"
>
<i className="mdi mdi-trash-can-outline" style={{ fontSize: '1.5rem' }}  ></i>
</span>

                                    {/* <button
                                        type="button"
                                        className="btn btn-sm btn-danger"
                                        onClick={() => removeAttachment(index)}
                                    >
                                        Remove
                                    </button> */}
                                </li>
                            ))}
                        </ul>
                    )}


                            <DataTable value={attachmentdata}>
                                <Column headerStyle={{ textAlign: 'center' }} header="#" body={(_, { rowIndex }) => rowIndex + 1} />
                             
                               <Column field="AttachmentName"    body={actionMemoBodyTemplate} header="Attachment"   className="text-left" filterPlaceholder="Search by Attachment" />
                                {/* <Column headerStyle={{ textAlign: 'center' }} field="AttachmentName" header="Attachment Name" /> */}

                            </DataTable>

                </ModalBody>
                <ModalFooter>

                    <Button color="secondary" onClick={toggleAttachmentModal}>Close</Button>
                </ModalFooter>
            </Modal>

        </React.Fragment>
    );
};

export default AddPurchaseMemo

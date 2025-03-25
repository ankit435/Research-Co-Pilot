import { Button, List, theme, Input, Typography, message, Select } from "antd";
import React, { useState, useRef, useEffect } from "react";
import { UploadOutlined, DeleteOutlined, EditOutlined, SaveOutlined, PlusOutlined, BoldOutlined, ItalicOutlined, UnderlineOutlined, OrderedListOutlined, UnorderedListOutlined } from "@ant-design/icons";
import AIChat from "./Chat/AIChat";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Bold from "@tiptap/extension-bold";
import Italic from "@tiptap/extension-italic";
import BulletList from "@tiptap/extension-bullet-list";
import OrderedList from "@tiptap/extension-ordered-list";
import ListItem from "@tiptap/extension-list-item";
import { Picker } from 'emoji-mart';
import { useAuth } from "../utils/auth";
import ResizableLayout from '../../src/components/Layout/ResizableLayouts';
import './Chat/PDFWindow.css';
import JSZip from 'jszip'; // Import JSZip for unzipping files
import { over } from "lodash";
// import 'emoji-mart/css/emoji-mart.css';
// import Underline from "./extensions/Underline"; 

const { useToken } = theme;
const { TextArea } = Input;
const { Option } = Select;
const { Text } = Typography;

const EmojiPicker = ({ onSelect }) => {
    return (
        <Picker
            onSelect={(emoji) => onSelect(emoji.native)}
            style={{ position: 'absolute', bottom: '60px', right: '20px' }}
        />
    );
};

const PDFWindow = () => {
    const [files, setFiles] = useState([]);
    const [loading, setLoading] = useState(false);
    const [searchWeb, setSearchWeb] = useState(false); // State for checkbox
    const { SetaddUploadedFiles } = useAuth(); // Get the function to add uploaded files
    const fileInputRef = useRef(null); // Create a ref for the file input
    const [hoveredItemIndex, setHoveredItemIndex] = useState(null); // 

    const handleFileUpload = async (event) => {
        const uploadedFiles = Array.from(event.target.files);
        const validFiles = [];

        for (const file of uploadedFiles) {
            if (file.type === 'application/pdf') {
                validFiles.push(file);
            } else if (file.type === 'application/zip') {
                console.log("zip found"); // Log message for ZIP files
                validFiles.push(file);
            }
        }

        if (validFiles.length !== uploadedFiles.length) {
            message.error('Only PDF and ZIP files are allowed.');
        }

        setFiles((prevFiles) => [...prevFiles, ...validFiles]);
        event.target.value = null; // Reset input value to allow re-upload of the same file

        await uploadFiles(validFiles);
    };

    const handleRemoveFile = (fileToRemove) => {
        setFiles((prevFiles) =>
            prevFiles.filter((file) => file.name !== fileToRemove.name)
        );
    };

    const uploadFiles = async (validFiles) => {
        const pdfFilesToUpload = [];

        // Process each file and prepare for upload
        for (const file of validFiles) {
            if (file.type === 'application/pdf') {
                pdfFilesToUpload.push(file);
            } else if (file.type === 'application/zip') {
                console.log("called")
                const zip = new JSZip();
                const content = await zip.loadAsync(file);
                // Extract PDF files from ZIP
                for (const filename of Object.keys(content.files)) {
                    if (filename.endsWith('.pdf')) {
                        const pdfBlob = await content.files[filename].async('blob');
                        pdfFilesToUpload.push(new File([pdfBlob], filename));
                    }
                }
            }
        }

        // Add all valid PDF files to the auth context
        SetaddUploadedFiles(pdfFilesToUpload);

        // Uploading logic
        const formData = new FormData();
        pdfFilesToUpload.forEach(pdfFile => {
            formData.append('files', pdfFile);
        });

        setLoading(true);
        // try {
        //     const response = await fetch('/api/get_list_documents/', {
        //         method: 'POST',
        //         headers: {
        //             'Authorization': `Bearer ${localStorage.getItem('token')}`,
        //         },
        //         body: formData,
        //     });

        //     if (!response.ok) {
        //         throw new Error(`Upload failed: ${response.statusText}`);
        //     }

        //     const data = await response.json();
        //     message.success('Files uploaded successfully');
        //     console.log('Uploaded file names:', data.file_names);
        //     setFiles([]); // Clear files after successful upload
        // } catch (error) {
        //     message.error(error.message);
        // } finally {
        //     setLoading(false);
        // }
    };

    const handleOpenFileInput = () => {
        if (fileInputRef.current) {
            fileInputRef.current.click(); // Programmatically click the hidden file input
        }
    };

    return (
        <div className="pdf-window" style={{ padding: "2px", height: "100%" }}>

            <Button
                type="primary"
                onClick={handleOpenFileInput} // Open file input directly
                icon={<UploadOutlined />}
                style={{ marginBottom: "10px", width: '100%' }}
            >
                Add Source
            </Button>

            <input
                type="file"
                multiple
                accept=".pdf,.zip" // Accept only PDF and ZIP files
                onChange={handleFileUpload}
                style={{ display: 'none' }} // Hide the file input
                ref={fileInputRef} // Attach ref to the input
            />

            <List
                dataSource={files}
                renderItem={(file, index) => (
                    <List.Item
                        style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            backgroundColor: hoveredItemIndex === index ? '#1E1E1E' : '#292929', // Background color for list items with hover effect
                            borderRadius: "4px",
                            marginBottom: "10px", // Space between list items
                            padding: "10px", // Padding inside list items
                            transition: "background-color 0.3s ease",
                        }}
                        onMouseEnter={() => setHoveredItemIndex(index)}
                        onMouseLeave={() => setHoveredItemIndex(null)}
                    >
                        <span style={{ color: '#ffffff', flexGrow: 1 }}>{file.name}</span>
                        <DeleteOutlined
                            onClick={() => handleRemoveFile(file)}
                            style={{ color: 'red', cursor: 'pointer' }}
                        />
                    </List.Item>
                )}
            />

            {/* Checkbox for searching the web */}

        </div>
    );
};

const NoteTaking = () => {
    const { token } = useToken();
    const [showEmojiPicker, setShowEmojiPicker] = useState(false);
    const [notes, setNotes] = useState([]);
    const [currentTitle, setCurrentTitle] = useState("");
    const [currentNoteIndex, setCurrentNoteIndex] = useState(null);

    const editor = useEditor({
        extensions: [
            StarterKit.configure({
                heading: { levels: [1, 2, 3, 4, 5, 6] },
            }),
            Bold,
            Italic,
            // Underline,
            BulletList,
            OrderedList,
            ListItem,
        ],
        content: "",
        editorProps: {
            attributes: {
                class: "editor-content focus:outline-none bg-gray-900 text-white p-4 rounded-md",
                style: "min-height: 250px; max-height: 250px; overflow-y: auto;",
            },
        },
    });

    useEffect(() => {
        const savedNotes = JSON.parse(localStorage.getItem('notes')) || [];
        setNotes(savedNotes);
    }, []);

    useEffect(() => {
        localStorage.setItem('notes', JSON.stringify(notes));
    }, [notes]);

    const handleEmojiSelect = (emojiObject) => {
        editor.chain().focus().insertContent(emojiObject.emoji).run();
        setShowEmojiPicker(false);
    };

    const handleSave = () => {
        if (editor && currentTitle) {
            const newNote = {
                title: currentTitle,
                notes: editor.getHTML(),
            };

            if (currentNoteIndex !== null) {
                // Update existing note
                const updatedNotes = [...notes];
                updatedNotes[currentNoteIndex] = newNote;
                setNotes(updatedNotes);
            } else {
                // Add new note
                setNotes([...notes, newNote]);
            }

            // Reset fields
            setCurrentTitle("");
            editor.commands.clearContent();
            setCurrentNoteIndex(null);
        }
    };

    const deleteIconStyle = {
        display: "none",
        color: "red",
        fontSize: "16px",
        cursor: "pointer",
    };

    const addNewNote = () => {
        handleSave(); // Save existing note before adding a new one
        setCurrentTitle('');
        editor.commands.clearContent();
        setCurrentNoteIndex(null);
    };

    const handleEditNote = (index) => {
        setCurrentTitle(notes[index].title);
        editor.commands.setContent(notes[index].notes);
        setCurrentNoteIndex(index);
    };

    const handleDelete = (index) => {
        setNotes(notes.filter((_, i) => i !== index));
    };

    if (!editor) return null;

    return (
        <div style={{ padding: "2px", maxWidth: "800px", margin: "auto" }}>
            <Button type="primary" onClick={addNewNote} style={{ marginBottom: "10px", width: '100%' }}>
                New Note
            </Button>

            <Input
                placeholder="Enter note title"
                value={currentTitle}
                onChange={(e) => setCurrentTitle(e.target.value)}
                style={{ marginBottom: "10px" }}
            />

            {/* Toolbar */}
            <div style={{ display: "flex", gap: "8px", marginBottom: "10px", background: token.colorBgContainer, padding: "10px", borderRadius: "8px" }}>
                <Button onClick={() => editor.chain().focus().toggleBold().run()} type={editor.isActive("bold") ? "primary" : "default"} icon={<BoldOutlined />}>
                </Button>
                <Button onClick={() => editor.chain().focus().toggleItalic().run()} type={editor.isActive("italic") ? "primary" : "default"} icon={<ItalicOutlined />}>

                </Button>
                <Button onClick={() => editor.chain().focus().toggleUnderline().run()} type={editor.isActive("underline") ? "primary" : "default"} icon={<UnderlineOutlined />}>

                </Button>
                <Button onClick={() => editor.chain().focus().toggleBulletList().run()} type={editor.isActive("bulletList") ? "primary" : "default"} icon={<UnorderedListOutlined />}>
                </Button>
                <Button onClick={() => editor.chain().focus().toggleOrderedList().run()} type={editor.isActive("orderedList") ? "primary" : "default"} icon={<OrderedListOutlined />}>
                </Button>
                <Button onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()} type={editor?.isActive('heading', { level: 1 }) ? 'primary' : 'default'}>
                    H1
                </Button>
                <Button onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()} type={editor?.isActive('heading', { level: 2 }) ? 'primary' : 'default'}>
                    H2
                </Button>
                <Button onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()} type={editor?.isActive('heading', { level: 3 }) ? 'primary' : 'default'}>
                    H3
                </Button>
                <Button onClick={() => setShowEmojiPicker(!showEmojiPicker)}>😊 Emoji</Button>

                {showEmojiPicker && (
                    <EmojiPicker onEmojiClick={handleEmojiSelect} style={{ position: 'absolute', bottom: '60px', right: '20px' }} />
                )}
            </div>

            {/* Editor */}
            <EditorContent editor={editor} style={{ background: token.colorBgContainer, padding: "10px", border: `1px solid ${token.colorBorder}` }} />

            {/* Save Button */}
            <Button type="primary" onClick={handleSave} disabled={!currentTitle} style={{ marginTop: "20px" }}>
                Save Note
            </Button>

            <Typography.Title level={4}>Saved Notes</Typography.Title>
            <List dataSource={notes} renderItem={(note, index) => (
                <List.Item
                    actions={[
                        <EditOutlined key="edit" onClick={() => handleEditNote(index)} />,
                        <DeleteOutlined key="delete" onClick={() => handleDelete(index)} className="delete-icon" />
                    ]}
                    style={{
                        cursor: 'pointer',
                        transition: 'background-color 0.3s',
                        border: '1px solid #444444',
                        borderRadius: '4px',
                        padding: '10px',
                        '&:hover': {
                            backgroundColor: '#f0f0f0'
                        }
                    }}
                    className="note-item"
                    onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#333333'}
                    onMouseLeave={(e) => e.currentTarget.style.backgroundColor = ''}
                >
                    <Typography.Text strong>{note.title}</Typography.Text>
                </List.Item>
            )} />
        </div>
    );
};

const AiAssistant = () => {
    const { token } = useToken();
    const [selectedAgent, setSelectedAgent] = useState("pdf_agent");

    const handleChange = (value) => {
        setSelectedAgent(value);
    };

    const containerStyle = {
        height: "92vh",
        background: token.colorBgContainer,
        display: "flex",
        flexDirection: "column",
    };

    const rowStyle = {
        display: "flex",
        overflow: "hidden",
        margin: "10px",
        height: "100%"
    };

    const boxStyle = {
        height: "100%",
        background: token.colorBgContainer,
        border: `1px solid ${token.colorBorder}`,
        borderRadius: token.borderRadiusLG,
        color: token.colorText,
        display: "flex",
        flexDirection: "column",
    };


    const headingStyle = {
        margin: "10px",
        borderBottom: `1px solid ${token.colorBorder}`, // Use token for border
        paddingBottom: "5px",
        color: token.textColorHeading, // Assuming you have a specific heading color token
    };

    const contentStyle = {
        flex: 1,
        msOverflowStyle: 'none',
        overflowY: "auto", // Allow vertical scrolling
        padding: "10px", // Padding for better spacing
        maxHeight: "500px",

       
        scrollbarWidth: 'none',
        msOverflowStyle: 'none',
        '&::-webkit-scrollbar': {
            display: 'none'}

        
    };

    const headingStyleChatbox = {
        margin: "0px 10px",
        borderBottom: `1px solid ${token.colorBorder}`, // Use token for border
        color: token.textColorPrimary, // Use token for text color
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        height: "37px",
    };

    const dropdownContainerStyle = {
        display: "flex",
        alignItems: "center", // Center label and dropdown vertically
    };

    const agentLabelStyle = {
        marginRight: '10px', // Increase spacing to the right of the label
    };

    const selectStyle = {
        width: '150px', // Set a fixed width for better appearance
        height: '30px', // Maintain height
    };

     return (
        <div style={containerStyle}>
            <div style={rowStyle}>
                <ResizableLayout>
                    {/* Sources Panel */}
                    <div style={boxStyle}>
                        <h3 style={headingStyle}>Sources</h3>
                        <div style={contentStyle}>
                            <PDFWindow />
                        </div>
                    </div>

                    {/* Chat Panel */}
                    <div style={{
                        height: "100%",
                        border: `1px solid ${token.colorBorder}`,
                        borderRadius: token.borderRadiusLG,
                        color: token.colorText,
                        background: token.colorBgContainer,
                    }}>
                        <div style={headingStyleChatbox}>
                            <h3 style={{ color: token.colorText }}>Chat</h3>
                            <div style={dropdownContainerStyle}>
                                <Text strong style={agentLabelStyle}>Agent:</Text>
                                <Select
                                    value={selectedAgent}
                                    onChange={handleChange}
                                    style={selectStyle}
                                    placeholder="Select an agent"
                                >
                                    <Option value="web_agent">Web</Option>
                                    <Option value="pdf_agent">PDF</Option>
                                </Select>
                            </div>
                        </div>
                        <div style={{
                            maxHeight: '84vh',
                            minHeight: '84vh',
                            overflow: "hidden",
                            padding: token.padding,
                            display: "flex",
                        }}>
                            <div style={{
                                flex: 1,
                                background: token.colorBgContainer,
                                borderRadius: token.borderRadiusLG,
                            }}>
                                <AIChat aiAssistant={true} aiAgent={selectedAgent} />
                            </div>
                        </div>
                    </div>

                    {/* Notes Panel */}
                    <div style={boxStyle}>
                        <h3 style={headingStyle}>Notes</h3>
                        <div style={contentStyle}>
                            <NoteTaking />
                        </div>
                    </div>
                </ResizableLayout>
            </div>
        </div>
    );
};

export default AiAssistant;
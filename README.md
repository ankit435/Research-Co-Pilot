# Research Assistant WebApp

# 📚 Project Overview  

Welcome to the **Research Assistant WebApp** developed by **Team Tech Titans**  
👨‍💻 **Pavan** | 👨‍💻 **Dheeraj** | 👨‍💻 **Ankit** | 👨‍💻 **Krishna**  

This application is designed to revolutionize the way researchers interact with academic papers.  
Built with **🐍 Django** (backend) and **⚛️ React** (frontend), it leverages **🌐 Django Rest Framework (DRF)** for APIs and **🔐 JWT Authentication** for secure user access.  

---

## 🚀 Key Features  

### 📝 **1. Research Paper Analytics**  
📊 Track user engagement with research papers:  
- 📑 Monitor the number of papers read.  
- ⏳ Analyze the time spent on each paper.  
- 📆 Generate month-on-month research activity statistics.  

---

### 🎯 **2. Smart Recommendation System**  
🔍 Suggests **relevant research papers** based on:  
- 📌 User's **bookmarked** papers.  
- 📖 Previously **read** papers.  

📷 The image below shows our **Recommendation Logic**:  
![Recommendation System](https://github.com/user-attachments/assets/e79ea5e6-5811-4a00-b867-d77add20046f)  

---

### 🗒️ **3. Research Assistant Page**  
✍️ Users can:  
- 📌 **Take detailed notes** on research papers.  
- 💬 Access an **AI-powered chatbot** for:  
  - 📰 **Summarizing** research content.  
  - ❓ **Answering questions** within the context of the paper.  

---

### 🌍 **4. Web Agent Integration**  
🔎 Enables users to:  
- 🌐 **Search the internet** for relevant research materials.  
- 📂 **Upload ZIP files** containing PDFs:  
  - 📜 The app **unzips & processes** PDFs automatically.  
  - 🤖 Users can **interact** with the uploaded documents via chat.  

---

### 💬 **5. Collaborative Chat Functionality**  
👥 **Group Chats** for researchers with similar interests.  
🧠 Integrated **Research Agent**:  
- 🔖 Get answers to queries by tagging the bot (`@bot`).  
- 📚 **AI-powered assistance** for research-related questions.  

---

🚀 **Join us in revolutionizing academic research!** 🎓  

---

## 🚀 Technology Stack  

### 🖥️ Backend  
- **🐍 Django**: Provides a robust framework for backend development.  
- **🌐 Django Rest Framework (DRF)**: Exposes APIs for seamless interaction between the frontend and backend.  
- **🔐 JWT Authentication**: Ensures secure login and access management.  

### 🎨 Frontend  
- **⚛️ React**: Offers a dynamic and responsive user interface.  

### 🔗 Other Integrations  
- **🤖 Chatbot**: Summarizes research papers and answers context-based questions.  
- **🌍 Web Agent**: Searches the internet and processes uploaded documents.  
- **💬 Group Chat**: Enhances collaborative research.  


### Models Used
# AI Models and Technologies Used

## 🚀 Models and Their Use Cases  

- **Llama-3.3-70B-Versatile**  
  - Used for **Q&A** to provide accurate and contextual answers.  
  - Powers the **Web Agent** for retrieving real-time information.  
- **Llama-3-8B-8192**  
  - Optimized for **Summarization**, generating concise and relevant summaries.  
- **OpenCLIP**  
  - Handles **Image Processing**, enabling image recognition and text-to-image tasks.  
- **Llama-3.2-90B-Vision-Preview**  
  - Used for **Image Explanation**, providing detailed descriptions and insights.  
## 📌 Embeddings and Vector Search  
- **Sentence-Transformers/all-MiniLM-L6-v2**  
  - Used for **Text Embeddings**, converting text into dense vectors for similarity comparisons.  
- **FAISS (Facebook AI Similarity Search)**  
  - High-performance **Vector Database** for fast and efficient similarity searches.  
## 🔍 Recommendation System  
- **Cosine Similarity & TF-IDF Vectors**  
  - Used for **Recommendations**, measuring text similarity and ranking relevant content.  

---

## Installation and Setup

### Prerequisites
- Python 3.9+
- Node.js 16+
- npm or yarn

### Backend Setup
1. Clone the repository.
2. Navigate to the backend directory:
   ```bash
   cd Server/ReSearch
   ```
3. Create a virtual environment and activate it:
   ```bash
   python -m venv env
   source env/bin/activate  # For Windows: env\Scripts\activate
   ```
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Apply migrations:
   ```bash
   python manage.py migrate
   ```
6. To start the development server and access the Django Admin Page, run:
   ```bash
   python manage.py runserver
   ```
   - To create super-user to access the Django Admin Pannel
     ```bash
     python manage.py createsuperuser
     ```
7. For running the application 
  ```bash
   uvicorn ReSearch.asgi:application --reload
   ```

### Frontend Setup
1. Navigate to the frontend directory:
   ```bash
   cd Client/copilotall
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the development server:
   ```bash
   npm start
   ```

---

## Usage
1. Register and log in to the application.
2. Explore research papers, make notes, and track your analytics.
3. Upload ZIP files or use the web agent to find and chat with relevant research papers.
4. Collaborate with other researchers using group chat.
5. Leverage the chatbot for summarization and query resolution.

---

## Team Members
- **Pavan**
- **Dheeraj**
- **Ankit**
- **Krishna**

---

## Future Enhancements
- Integrating machine learning models for more accurate recommendations.
- Adding support for additional file formats (e.g., Word documents).
- Enhancing analytics with advanced visualizations.

---

## Contributing
Contributions are welcome! Please fork the repository and create a pull request with your changes.

---
## Test Coverage Details
- We achieved overall code coverage of 77% through test case
- Line coverage - 81%
- Branch coverage - 72%
![image](https://github.com/user-attachments/assets/2487de8d-ac4b-4c87-b3b9-e768a4fbec4f)

![image](https://github.com/user-attachments/assets/a0fbbc4e-22bc-475c-a5bb-b71a797e91fd)

![image](https://github.com/user-attachments/assets/b01d70f7-e9a1-415e-ba00-20ee8d24336f)
---

Thank you for exploring the Research Assistant WebApp! Together, let's make research more effective and efficient.
- Team TechTitans :ship:


import json
import logging
import os
import subprocess
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from src.score_calculation import calculate_faithfulness_score
from src.prompts import build_prompts
from src.themes_processor import process_text_with_themes  # Used to extract themes
from src.actor_processor import process_text_with_actors  # Used to extract actors

logger = logging.getLogger(__name__)

# Modificar el modelo DocumentReport para incluir actor_descriptions
class DocumentReport(BaseModel):
    """Structure for the document report."""
    title: str = Field(description="Document title")
    date: str = Field(description="Document date in YYYY-MM-DD or YYYY-MM format")
    location: str = Field(description="Principal location")
    executive_summary: str = Field(description="Executive summary of the document")
    characteristics: List[str] = Field(description="Key characteristics as bullet points")
    themes: Dict[str, List[str]] = Field(description="Main themes categorized")
    actors: Dict[str, List[str]] = Field(description="Key actors and stakeholders categorized")
    practical_applications: List[str] = Field(description="Existing practical applications")
    commitments: List[str] = Field(description="Future quantifiable commitments")
    faithfulness_score: Optional[int] = Field(description="Faithfulness score (0-100)", default=None)
    # Nuevo campo para almacenar las descripciones de actores
    

def process_text_with_prompts(text: str, llm) -> DocumentReport:
    """
    Process document text with various prompts to extract structured information.
    
    Args:
        text: Text content from PDF document
        llm: Language model instance
        
    Returns:
        DocumentReport object with extracted information
    """
    prompts = build_prompts()
    results = {}
    
    logger.info("Applying prompts to document text...")
    
    # Process each prompt (except themes and actors, which are processed separately)
    for field, prompt in prompts.items():
        if field == "actors":
            # Skip actors as they will be processed separately
            continue
            
        try:
            logger.info(f"Extracting {field}...")
            chain = prompt | llm
            response = chain.invoke({"text": text})
            
            if field in ["characteristics", "practical_applications", "commitments"]:
                bullet_points = []
                for line in response.content.strip().split("\n"):
                    line = line.strip()
                    if line.startswith("- "):
                        bullet_points.append(line[2:])
                    elif line and not any(s in line for s in [":", "bullet", "point"]):
                        bullet_points.append(line)
                
                results[field] = bullet_points
            else:
                results[field] = response.content.strip()
                
        except Exception as e:
            logger.error(f"Error processing {field}: {e}")
            if field in ["characteristics", "practical_applications", "commitments"]:
                results[field] = ["Processing failed"]
            else:
                results[field] = "Processing failed"
    
    # Process themes separately using themes_processor
    logger.info("Extracting themes via themes_processor...")
    try:
        results["themes"] = process_text_with_themes(text, llm)
    except Exception as e:
        logger.error(f"Error processing themes: {e}")
        results["themes"] = {}
        
    # Process actors separately using actor_processor
    logger.info("Extracting actors via actor_processor...")
    try:
        results["actors"] = process_text_with_actors(text, llm)
    except Exception as e:
        logger.error(f"Error processing actors: {e}")
        results["actors"] = {}
    
    try:
        results["faithfulness_score"] = calculate_faithfulness_score(
            source_text=text,
            generated_content=results,
            llm=llm
        )
    except Exception as e:
        logger.error(f"Error calculating faithfulness score: {e}")
        results["faithfulness_score"] = None
    
    return DocumentReport(
        title=results.get("title", "Untitled Document"),
        date=results.get("date", "No date available"),
        location=results.get("principal_location", "Unknown location"),
        executive_summary=results.get("executive_summary", "No summary available"),
        characteristics=results.get("characteristics", []),
        themes=results.get("themes", {}),
        actors=results.get("actors", {}),
        practical_applications=results.get("practical_applications", []),
        commitments=results.get("commitments", []),
        faithfulness_score=results.get("faithfulness_score")
    )

# Modificar la función generate_markdown_report para que utilice el campo actor_descriptions del reporte
def generate_markdown_report(report: DocumentReport, entity_data: Dict[str, List]) -> str:
    """
    Generate a markdown report from the extracted information.
    
    Args:
        report: DocumentReport object with extracted information
        entity_data: Dictionary containing entities extracted from the document
        
    Returns:
        Markdown formatted report
    """
    md_lines = []
    
    # Add faithfulness score
    if report.faithfulness_score is not None:
        score = report.faithfulness_score
        rating = "Excellent" if score >= 80 else "Regular" if score >= 60 else "Poor"
        md_lines.append(f"**Faithfulness Score**: {score}/100 - {rating}")
        md_lines.append("")
    
    # Add title
    md_lines.append(f"# {report.title}")
    md_lines.append("")
    
    # Add date and location
    md_lines.append(f"**Date**: {report.date}")
    md_lines.append("")
    md_lines.append(f"**Location**: {report.location}")
    md_lines.append("")
    
    # Add executive summary
    md_lines.append("")
    md_lines.append("## Executive Summary")
    md_lines.append("")
    md_lines.append(report.executive_summary)
    md_lines.append("")
    
    # Add characteristics
    md_lines.append("")
    md_lines.append("## Characteristics")
    md_lines.append("")
    for char in report.characteristics:
        md_lines.append(f"- {char}")
    md_lines.append("")
    
    # Add actors and stakeholders table
    md_lines.append("## Actors")
    md_lines.append("")
    if report.actors:
        md_lines.append("| Category | Actor |")
        md_lines.append("| --- | --- |")
        for actor_category, actors in report.actors.items():
            actors_str = "; ".join(actors)
            md_lines.append(f"| {actor_category} | {actors_str} |")
        md_lines.append("")
    else:
        md_lines.append("No actors identified.")
        md_lines.append("")

    # Add themes as table (agrupados)
    md_lines.append("## Main Themes")
    md_lines.append("")
    if report.themes:
        md_lines.append("| Category | Subcategory |")
        md_lines.append("| --- | --- |")
        for main_theme, subs in report.themes.items():
            subs_str = "; ".join(subs)
            md_lines.append(f"| {main_theme} | {subs_str} |")
        md_lines.append("")
    else:
        md_lines.append("No themes identified.")
        md_lines.append("")
    
    # Add practical applications
    md_lines.append("## Practical Applications")
    md_lines.append("")
    if report.practical_applications:
        for app in report.practical_applications:
            md_lines.append(f"- {app}")
    else:
        md_lines.append("No practical applications identified.")
    
    # Add commitments
    md_lines.append("")
    md_lines.append("## Commitments")
    md_lines.append("")
    if report.commitments:
        for commit in report.commitments:
            md_lines.append(f"- {commit}")
    else:
        md_lines.append("No specific commitments identified.")
    
    return "\n".join(md_lines)

def save_report(markdown_content: str, report: DocumentReport, output_dir: str, filename_base: str) -> Dict[str, str]:
    """
    Save report in markdown, convert to Word, and save structured data as JSON.
    
    Args:
        markdown_content: Report content in markdown format
        report: DocumentReport object with structured data
        output_dir: Directory to save the report
        filename_base: Base filename without extension
        
    Returns:
        Dictionary with paths to created files
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Paths
    md_path = os.path.join(output_dir, f"{filename_base}.md")
    docx_path = os.path.join(output_dir, f"{filename_base}.docx")
    json_path = os.path.join(output_dir, f"{filename_base}.json")
    
    # Save markdown
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(markdown_content)
    
    # Save JSON with structured data
    with open(json_path, 'w', encoding='utf-8') as f:
        # Convert report to dict and save as JSON
        json.dump(report.model_dump(), f, ensure_ascii=False, indent=2)
    
    # Convert to Word using Pandoc
    try:
        subprocess.run(['pandoc', md_path, '-o', docx_path], check=True)
        logger.info(f"Successfully converted to Word: {docx_path}")
    except Exception as e:
        logger.error(f"Error converting to Word: {e}")
    
    return {
        "markdown": md_path,
        "docx": docx_path,
        "json": json_path
    }

def generate_report(text: str, entities: Dict[str, Any], llm, output_dir: str, folder_name: str) -> Dict[str, str]:
    """
    Process text, generate report and save to files.
    
    Args:
        text: Text content extracted from PDF
        entities: Dictionary of extracted entities
        llm: Language model instance
        output_dir: Output directory path
        folder_name: Name of the folder/document
        
    Returns:
        Dictionary with paths to created files
    """
    logger.info(f"Generating report for {folder_name}...")
    report = process_text_with_prompts(text, llm)
    
    # Generate markdown from the report
    markdown = generate_markdown_report(report, entities)
    
    # Pass both markdown content and report object to save_report
    return save_report(markdown, report, output_dir, folder_name)
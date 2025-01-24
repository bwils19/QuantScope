import pandas as pd
import numpy as np
import re
from file_handlers import analyze_column_content


def clean_column_name(name):
    """Clean column name for comparison"""
    # Convert to lowercase and remove special characters
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', '', name.lower())
    # Replace underscores and multiple spaces with single space
    cleaned = re.sub(r'[_\s]+', ' ', cleaned)
    return cleaned.strip()


def get_name_similarity(column_name, reference_terms):
    """Get similarity between column name and reference terms with improved cleaning"""
    column_name = clean_column_name(column_name)
    column_words = set(column_name.split())

    max_similarity = 0
    for term in reference_terms:
        term = clean_column_name(term)
        term_words = set(term.split())

        # Check for exact match after cleaning
        if column_name == term:
            return 1.0

        # Check for word matches
        intersection = column_words.intersection(term_words)
        if intersection:
            similarity = len(intersection) / max(len(column_words), len(term_words))
            max_similarity = max(max_similarity, similarity)

        # Check for substring matches (e.g., "sym" in "symbol")
        if column_name in term or term in column_name:
            similarity = len(min(column_name, term, key=len)) / len(max(column_name, term, key=len))
            max_similarity = max(max_similarity, similarity)

    return max_similarity


def smart_detect_columns(df):
    """Enhanced smart column detection"""
    column_mappings = {
        'ticker': ['ticker', 'symbol', 'stock', 'security'],
        'amount': ['amount', 'shares', 'quantity', 'owned', 'units'],
        'purchase_date': ['date', 'purchased', 'acquisition', 'entry'],
        'price': ['price', 'cost', 'value']
    }

    detected_columns = {}

    for col in df.columns:
        content_scores = analyze_column_content(df, col)
        best_match = None
        best_score = 0

        for target_col, reference_terms in column_mappings.items():
            # Get name similarity score
            name_score = get_name_similarity(col, reference_terms)
            # Get content score
            content_score = content_scores.get(target_col, 0)

            # Combine scores with weights
            combined_score = (name_score * 0.6) + (content_score * 0.4)

            if combined_score > best_score and combined_score > 0.3:  # Lowered threshold
                best_score = combined_score
                best_match = target_col

        if best_match:
            detected_columns[col] = best_match

    return detected_columns


def create_test_cases():
    """Create test cases with expected mappings"""
    test_cases = {}

    # Test 1: Mixed case and special characters
    test_cases["Mixed Case & Special Characters"] = {
        'data': pd.DataFrame({
            "StOcK_SyMbOl!!!": ["AAPL", "GOOGL", "MSFT"],
            "sHaReS_owned@@": [100, 200, 300],
            "Purchase$$Date": ["2023-01-01", "2023-02-01", "2023-03-01"]
        }),
        'expected_mappings': {
            "StOcK_SyMbOl!!!": "ticker",
            "sHaReS_owned@@": "amount",
            "Purchase$$Date": "purchase_date"
        }
    }

    # Test 2: Ambiguous column names
    test_cases["Ambiguous Names"] = {
        'data': pd.DataFrame({
            "identifier": ["AAPL", "GOOGL", "MSFT"],
            "number": [100, 200, 300],
            "value": [150.5, 250.5, 350.5]
        }),
        'expected_mappings': {
            "identifier": "ticker",
            "number": "amount",
            "value": "price"
        }
    }

    return test_cases


def print_detection_results(case_name, results, expected_mappings):
    """Print results with expected vs actual comparison"""
    print(f"\n{'=' * 80}")
    print(f"Test Case: {case_name}")
    print(f"{'=' * 80}")

    print("\n1. Input Columns:")
    for col in results["input_columns"]:
        print(f"  - {col}")

    print("\n2. Column Mappings:")
    print("  Expected:")
    for col, mapping in expected_mappings.items():
        print(f"    {col} → {mapping}")

    print("\n  Actual:")
    if results["detected_mappings"]:
        for col, mapping in results["detected_mappings"].items():
            status = "✓" if mapping == expected_mappings.get(col) else "✗"
            print(f"    {col} → {mapping} {status}")
    else:
        print("    No mappings detected!")

    print("\n3. Detailed Analysis:")
    for col, analysis in results["column_analysis"].items():
        print(f"\n  Column: {col}")
        print("  Sample values:", analysis["sample_values"])
        print("  Type detection scores:")
        for metric, score in analysis["type_scores"].items():
            print(f"    - {metric}: {score:.2f}")


def run_column_detection_tests():
    """Run tests with improved output"""
    test_cases = create_test_cases()

    for case_name, case_data in test_cases.items():
        df = case_data['data']
        expected_mappings = case_data['expected_mappings']

        results = {
            "input_columns": df.columns.tolist(),
            "detected_mappings": smart_detect_columns(df),
            "column_analysis": {
                col: {
                    "type_scores": analyze_column_content(df, col),
                    "sample_values": df[col].head().tolist()
                }
                for col in df.columns
            }
        }

        print_detection_results(case_name, results, expected_mappings)


if __name__ == "__main__":
    run_column_detection_tests()
import pandas as pd

# 1. Load your actual dataset
csv_file = "extracted_simulation_data.csv"
df = pd.read_csv(csv_file)

# 2. Output SCAPS script file names
num_scripts = 3
your_caps_file = "baseSim.scaps"

print(f"Generating {num_scripts} SCAPS batch scripts for {len(df)} configurations...")


def write_script(chunk_df, output_name):
    with open(output_name, "w") as f:
        # --- SCAPS Environment Setup ---
        f.write("clear\n")
        f.write(f'load definitionfile "{your_caps_file}"\n')

        # SCAPS native method to select calculation modes (1 = Active, 0 = Disabled)
        f.write(" action.iv 1\n")
        f.write(" action.cv 0\n")
        f.write(" action.cf 0\n")
        f.write(" action.qe 0\n\n")

        # --- Generate commands for every row in this chunk ---
        for _, row in chunk_df.iterrows():
            sim_id = row['simulation_id']
            f.write(f"// ===== Running Configuration: {sim_id} =====\n")

            # Layer 1: ETL (PCBM)
            f.write(f"set layer(1).thickness {row['L1_L']}\n")
            f.write(f"set layer(1).nd {row['L1_N_D']}\n")
            f.write(f"set layer(1).na {row['L1_N_A']}\n")

            # Layer 2: Active Layer (Perovskite Absorber)
            f.write(f"set layer(2).thickness {row['L2_L']}\n")
            f.write(f"set layer(2).nd {row['L2_N_D']}\n")
            f.write(f"set layer(2).na {row['L2_N_A']}\n")

            # Layer 3: HTL (PEDOT)
            f.write(f"set layer(3).thickness {row['L3_L']}\n")
            f.write(f"set layer(3).nd {row['L3_N_D']}\n")
            f.write(f"set layer(3).na {row['L3_N_A']}\n")

            # In SCAPS script, use 'calculate' alone to execute
            f.write("calculate\n")

            # SCAPS native format to export IV data curves
            f.write(f'save results.iv "{sim_id}_validation.iv"\n\n')

        f.write("show message 'Batch validation complete! Ready for evaluation.'\n")


# Split the dataset into 3 roughly equal parts
chunk_size = len(df) // num_scripts
remainder = len(df) % num_scripts
start = 0

for part in range(num_scripts):
    size = chunk_size + (1 if part < remainder else 0)
    part_df = df.iloc[start:start + size]
    start += size

    output_name = f"validate_simulations_part{part + 1}.script"
    write_script(part_df, output_name)
    print(f"Created '{output_name}' with {len(part_df)} configurations.")

print("Finished generating the three validation scripts.")
# -*- coding: utf-8 -*-
# pylint: disable=invalid-name,line-too-long,too-many-lines,too-many-arguments,too-many-locals,too-many-statements
"""
This Recommendation uses integral digital products. They form an integral
part of the recommendation and may not be reproduced, by any means whatsoever,
without written permission of ITU.

The user should download the necessary digital maps that are used by this
implementation directly from ITU-R web site and place the files in the
folder ./maps. After that, the user should execute the script
contained in this file "initiate_digital_maps.py". The script produces the
necessary maps in .npz format

The following maps should be extracted in the folder ./maps:
From ITU-R P.2001-6 (https://www.itu.int/dms_pubrec/itu-r/rec/p/R-REC-P.2001-6-202509-I!!ZIP-E.zip)
DN_Median.txt, DN_SubSlope.txt, DN_SupSlope.txt, dndz_01.txt
Esarain_Mt_v5.txt, Esarain_Pr6_v5.txt, Esarain_Beta_v5.txt
FoEs0.1.txt, FoEs01.txt, FoEs10.txt, FoEs50.txt
h0.txt, surfwv_50_fixed.txt, TropoClim.txt

Author: Ivica Stevanovic (IS), Federal Office of Communications, Switzerland
Revision History:
Date            Revision
18SEP2024       Initial version (IS)  
"""

import os
import numpy as np

# Necessary maps
filepath = "./maps/"
filenames = ["DN_Median.txt", "DN_SubSlope.txt", "DN_SupSlope.txt", "dndz_01.txt", \
                  "Esarain_Mt_v5.txt", "Esarain_Pr6_v5.txt", "Esarain_Beta_v5.txt", \
                  "FoEs0.1.txt", "FoEs01.txt", "FoEs10.txt", "FoEs50.txt", \
                  "h0.txt", "surfwv_50_fixed.txt", "TropoClim.txt"]

# begin code
maps = dict();
failed = False
for filename in filenames:

      # Load the file into a NumPy array
      try:
            print(f"Processing file {filename}");
            if (filename == "TropoClim.txt"):
                  matrix = np.loadtxt(filepath + filename, dtype = 'int')
            else:
                  matrix = np.loadtxt(filepath + filename)
            # Print the NumPy array (matrix)
            key = filename[0:-4]
            if (key == "FoEs0.1"):
                  key = "FoEs0p1"

            maps[key] = matrix

      except OSError:
            print(f"Error: {filename} does not exist or cannot be opened.")
            failed = True
      except ValueError:
            print(f"Error: The file {filename} contains invalid data for a float matrix.")
            failed = True
      

if (not failed):
      # Save matrices using dynamically provided names
      np.savez_compressed('P2001.npz', **maps)

      print("P2001.npz file created successfully.")
      
else:
      print("The process failed. Make sure that the required maps are downloaded from ITU-R P.2001-6 and extracted to the folder ./maps")



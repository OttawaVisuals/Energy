# ERS Data Dictionary — Full Column Reference

Every column NRCan publishes in the EnerGuide/ERS open-data CSV extracts (433 columns, audit years 2004–2026), with its NRCan-authored description, how completely it's populated, and its cardinality. This is the full raw dataset — see [RETROFITS.md](RETROFITS.md) for the ~48 columns the [Retrofit Explorer](../retrofits.html) actually reads and how each is used.

**Updated 2026-07-31.** Fill rate and unique-value count are measured across **all 4,542,544 raw audit records** (every `D`/`E` evaluation in every yearly CSV, `C:\ERS\2004-2006.csv` … `2026.csv`) — this is the *unpaired* audit stream, not the smaller before/after-matched sample the Retrofit Explorer charts show, so these figures read a little more complete than what a single matched retrofit record has filled in. Descriptions are NRCan's own open-data column dictionary, unedited. Unique-value counts are capped at 20,000 distinct strings per column (shown as `>20000`) to keep a full-column-set scan bounded — exact cardinality isn't meaningful for near-unique identifier fields like `HOUSEID` or `EVALUATIONSID` anyway.

| Column | Description | % filled | Unique values |
|---|---|---:|---:|
| `ACCENTESTAR` | Central A/C is ENERGY STAR certified (ESTAR or N/A) | 11.9% | 1 |
| `ACMODELNUMBER` | Model number of the A/C or heat pump with Heating/Cooling | 47.7% | >20000 |
| `ACWINDESTAR` | Number of Window unit A/C that are ENERGY STAR certified (0,1,2,3,4...) | 94.2% | 16 |
| `ACWINDNUM` | Number of window unit A/C | 94.2% | 35 |
| `AHRI` | Used to indicate the AHRI number associated with a heat pump | 36.8% | 19254 |
| `AIR50P` | Air leakage at 50 pascals | 100.0% | >20000 |
| `AIRCONDTYPE` | Type of central A/C System (Central split System, Central single package system, Ductless Mini- or Multi-split system, Compact Ducted Mini- or Multi-split system, and Coils Only) or “Not installed” | 94.0% | 13 |
| `AIRCOP` | Coefficient of performance for A/C system | 94.2% | 3851 |
| `ASHPHSPF` | Indicates the heating efficiency of an Air Source Heat Pump (HSPF value or 0) | 7.2% | 643 |
| `ASHPHSPF2` | Indicates the heating efficiency of an Air Source Heat Pump (HSPF2 value or 0) | 7.2% | 398 |
| `ASHPSEER` | Indicates the cooling efficiency of an Air Source Heat Pump (SEER value or 0) | 7.2% | 770 |
| `ASHPSEER2` | Indicates the cooling efficiency of an Air Source Heat Pump (SEER2 value or 0) | 7.2% | 360 |
| `ATTICCEILINGDEF` | Description of attic insulation (displays percentage of attic area, followed by the nominal R-value) | 89.6% | >20000 |
| `ATYPICALENERGYLOADS` | Indicates presence of atypical energy loads (True or False) | 45.2% | 8 |
| `AUXENERGY` | Amount of energy required for annual space heating, calculated as the gross space heating energy load less the usable internal and solar heat gains (MJ) | 48.2% | >20000 |
| `BACKWATERVALVE` | Used to indicate the presence of a back water valve with alarm (1 = yes, 0 = no) | 36.7% | 4 |
| `BASELOADSMURB` | Total MURB base load energy (MJ/year) | 99.9% | 8292 |
| `BASEMENTFLOORAR` | Basement floor area (square metres) | 99.9% | >20000 |
| `BATTERYSTORAGE` | Indicates the presence of battery storage for PV system (1 = yes, 0 = no) | 36.7% | 4 |
| `BLOWERDOORTEST` | v11.12 (and earlier) files: Blower door test type (None, CGSB, As operated)  v11.13 files: As operated - User specified - Test Data – The blower door test data is available in HOT2000 As operated - User Specified – The energy advisor used external software (e.g. from the blower door manufacturer) to calculate ACH and ELA As operated - Calculated – A default ACH value was used and ELA was calculated by HOT2000 (e.g. when vermiculite is exposed to the interior environment, P files) or a 4-zone blower door test was completed | 97.3% | 13 |
| `BUILDINGTYPE` | Indicates what type of building is being assessed (House, Multi-unit: one unit, or Multi-unit: whole building) | 45.5% | 5 |
| `CAFLACEILINGDEF` | Description of cathedral or flat roof insulation (displays percentage of attic area, followed by nominal R-value) | 23.8% | >20000 |
| `CCASHP` | Indicates the presence of a cold climate heat pump (1 = yes, 0 = no) | 36.7% | 4 |
| `CCASHPCAP` | Contains the rated heating capacity of the cold climate ASHP at 8.3 °C (47 °F) in kW | 36.8% | 1747 |
| `CCASHPCAPACITYMAINTENANCE` | Contains the capacity maintenance percentage of the cold climate ASHP (Max -15 °C (5 °F)/Rated 8.3 °C | 36.8% | 530 |
| `CCASHPCOP` | Contains the coefficient of performance of the cold climate ASHP at -15 °C (5 °F) | 36.8% | 500 |
| `CCASHPHSPF` | Indicates the rated heating efficiency for a cold climate air source heat pump (HSPF (region IV) value or 0) | 36.8% | 738 |
| `CCASHPHSPF2` | Indicates the rated heating efficiency for a cold climate air source heat pump (HSPF2 (region V) value or 0) | 7.3% | 264 |
| `CCASHPSEER` | Indicates the rated cooling efficiency of a cold climate air source heat pump (SEER value or 0) | 36.8% | 978 |
| `CCASHPSEER2` | Indicates the rated cooling efficiency of  a cold climate air source heat pump (SEER2 value or 0) | 7.2% | 215 |
| `CEILINGTYPE` | Ceiling type (‘A’ for a gable/hip/scissor attic, or ‘F’ for a flat or cathedral attic) | 94.0% | 152 |
| `CEILINS` | Ceiling effective insulation RSI value | 100.0% | 1738 |
| `CENVENTSYSTYPE` | Ventilation type installed | 100.0% | 5 |
| `CLIENTCITY` | City (where property is located) | 100.0% | >20000 |
| `CLIENTPCODE` | Homeowner postal code (where property is located) Only first 3 digits provided. | 100.0% | 1693 |
| `COMMONHEATEDFLOORAREA` | Contains the heated floor area of all common areas (square metres) | 48.2% | 1697 |
| `COMMONSPACEELECCONS` | Displays the electrical consumption in kWh of the common space area | 48.2% | 3864 |
| `COP` | Heat pump coefficient of performance | 100.0% | 1789 |
| `CRAWLSPFLOORAR` | Crawl space floor area (square metres) | 99.9% | >20000 |
| `CREDITEGH` | EGH credit in kWh (only available for files prior to v11) | 99.9% | 1 |
| `CREDITGARAGE` | Attached garage credit in kWh (only available for files prior to v11) | 99.9% | 1399 |
| `CREDITLIGHTING` | Total lighting credit in kWh (only available for files prior to v11) | 99.9% | 29 |
| `CREDITOTH1OTH2` | Other credit in kWh (only available for files prior to v11) | 99.9% | 1073 |
| `CREDITPV` | Photovoltaic credit in kWh, capped to maximum electricity consumption | 99.9% | >20000 |
| `CREDITVENT` | Ventilation system credit in kWh (only available for files prior to v11) | 99.9% | 9 |
| `CREDITWIND` | Wind power credit in kWh | 99.9% | 50 |
| `CSHDR` | Crawl space header insulation (percentage of header area, followed by the nominal R-value) | 0.6% | 3254 |
| `CSIA` | Canadian Solar Industry Association rating for solar domestic hot water system (MJ/year) | 100.0% | 472 |
| `DATASET` | Flag that indicates if the data is for the standard operating conditions (SOC) house, or the reduced operating conditions (ROC) house | 47.4% | 2 |
| `DEPRESSEXHAUST` | Result of the exhaust devices depressurization test | 99.9% | 841 |
| `DHWHPCOP` | Domestic hot water heat pump system coefficient of performance | 100.0% | 234 |
| `DHWHPTYPE` | Domestic hot water heat pump system type | 0.4% | 4 |
| `DWHRL1M` | Drain-water heat recovery smaller than 1 meter | 94.2% | 6 |
| `DWHRM1M` | Drain-water heat recovery greater than 1 meter | 94.2% | 6 |
| `EGHCRITNATACH` | Critical natural air change per hour | 100.0% | 19139 |
| `EGHCRITTOTACH` | Critical total air change per hour | 100.0% | >20000 |
| `EGHDESHTLOSS` | Design heat loss (Watts) | 100.0% | >20000 |
| `EGHFCONELEC` | Consumption of electricity (kWh) | 100.0% | >20000 |
| `EGHFCONNGAS` | Consumption of natural gas (cubic metres) | 100.0% | >20000 |
| `EGHFCONOIL` | Consumption of oil (L) | 100.0% | >20000 |
| `EGHFCONPROP` | Consumption of propane (L) | 100.0% | >20000 |
| `EGHFCONTOTAL` | Total energy consumption (MJ) | 100.0% | >20000 |
| `EGHFCONWOOD` | Consumption of wood (tonne) | 100.0% | 610 |
| `EGHFCONWOODGJ` | Consumption of wood (GJ/year) | 43.4% | 3925 |
| `EGHFURNACEAEC` | Annual energy consumption for the heating system (MJ) | 100.0% | >20000 |
| `EGHFURSEASEFF` | Furnace Seasonal Efficiency | 100.0% | 4093 |
| `EGHHEATFCONSE` | Heating energy consumption - Base Electricity (kWh) | 94.2% | >20000 |
| `EGHHEATFCONSG` | Heating energy consumption - Base Natural Gas (cubic metres) | 94.2% | >20000 |
| `EGHHEATFCONSO` | Heating energy consumption - Base Oil (litres) | 94.2% | >20000 |
| `EGHHEATFCONSP` | Heating energy consumption - Base Propane (litres) | 94.2% | >20000 |
| `EGHHEATFCONSW` | Heating energy consumption - Base Wood (tonne) | 94.2% | >20000 |
| `EGHHLAIR` | Heat loss to air leakage (MJ) | 100.0% | >20000 |
| `EGHHLCEILING` | Heat loss to ceilings (MJ) | 100.0% | >20000 |
| `EGHHLEXPOSEDFLR` | Heat loss to exposed floor (MJ) | 100.0% | >20000 |
| `EGHHLFOUND` | Heat lost through foundation (MJ) | 100.0% | >20000 |
| `EGHHLWALLS` | Heat loss through walls (MJ) | 100.0% | >20000 |
| `EGHHLWINDOOR` | Heat loss through windows and doors (MJ) | 100.0% | >20000 |
| `EGHINEXPOSEDFLR` | Exposed floor effective insulation RSI value | 100.0% | 1277 |
| `EGHRATING` | EnerGuide rating for 0-100 scale (only available for files prior to v11) | 100.0% | 755 |
| `EGHSPACEENERGY` | Rated annual space heating energy consumption and ventilator electrical consumption (during heating hour) (MJ) | 100.0% | >20000 |
| `EIDEF` | Displays the exterior foundation wall definition (displays percentage of foundation exterior wall area, followed by the nominal R-value) | 41.1% | 9726 |
| `ELECAUTOCHRGSTATION` | Indicates presence of electrical charging station for an electric vehicle (True or False) | 45.2% | 4 |
| `ELGNBCCMP` | Indicates whether the proposed design is within the scope of what is eligible to use the performance compliance path of the NBC Section 9.36 (true or false value) | 25.2% | 4 |
| `ENERGYPERFORMANCETIER` | The proposed house’s resulting energy performance tier for the purpose of compliance to the Energy Performance Tiers in NBC 9.36.6 | 18.6% | 6 |
| `ENTRYDATE` | Evaluation date (the date when the evaluation was performed). Only the month and year are provided. | 100.0% | 322 |
| `ENVELOPEIMPROVEMENT` | For the purpose of compliance to the National Building Code Energy Performance Tiers, this value represents the energy performance improvement of the proposed house’s building envelope over that of the reference house | 18.6% | >20000 |
| `EPACSA` | Wood Fireplace or insert meets CSA-B415-M92 or 40 CFR Part10 (EPACSA or N/A) | 0.0% | 1 |
| `EPACSASUPPHTG1` | Supplementary Heating system 1 (solid fuel burning) meets CSA or EPA standard | 1.1% | 1 |
| `EPACSASUPPHTG2` | Supplementary Heating system 2 (solid fuel burning) meets CSA or EPA standard | 0.2% | 1 |
| `ERSELECGHG` | Rated Electricity Annual Green House Gas Emissions (tonnes/year) | 55.1% | 689 |
| `ERSENERGYINTENSITY` | Rated Energy Intensity (Actual EnerGuide System Rating divided by the heated floor area) | 55.1% | 654 |
| `ERSGHG` | Annual Green House Gas Emissions Total in tonnes/year | 55.1% | 743 |
| `ERSHLDOOR` | Heat loss to doors in GJ/year | 55.1% | >20000 |
| `ERSHLWINDOW` | Heat loss to windows in GJ/year | 55.1% | >20000 |
| `ERSLIGHTAPPLIANCEENERGY` | Rated Annual Energy Consumption for Lights and Appliances in MJ (Base Case - Standard Operating Conditions) | 55.1% | 4163 |
| `ERSNGASGHG` | Rated Natural Gas Annual Green House Gas Emissions (tonnes/year) | 55.1% | 448 |
| `ERSOILGHG` | Rated Oil Annual Green House Gas Emissions (tonnes/year) | 55.1% | 489 |
| `ERSOTHERELECENERGY` | Rated Annual Energy Consumption for Other Electrical in MJ (Base Case - Standard Operating Conditions) | 55.1% | 51 |
| `ERSPROPGHG` | Rated Propane Annual Green House Gas Emissions (tonnes/year) | 55.1% | 275 |
| `ERSRATING` | EnerGuide Rating System rating (GJ/year) | 55.1% | 1861 |
| `ERSREFHOUSEGHG` | Typical new house GHG emissions (tonnes/year) | 48.2% | 540 |
| `ERSREFHOUSERATING` | Typical new house EnerGuide System Rating (GJ/year) | 55.1% | 1287 |
| `ERSRENEWABLEELEC` | Total annual renewable energy produced by photovoltaic systems and wind turbines (MJ) | 55.1% | >20000 |
| `ERSRENEWABLEELECGHG` | Rated Annual Green House Gas Emissions that is offset by the Renewable Electricity Production in tonnes/year | 55.1% | 226 |
| `ERSRENEWABLEPROD` | Total Annual Renewable Energy Produced in MJ | 55.1% | >20000 |
| `ERSRENEWABLESOLAR` | Annual Solar Domestic Water Heating Energy Contribution in MJ | 55.1% | 675 |
| `ERSRENEWABLESOLARGHG` | Rated Annual Green House Gas Emissions that is offset by the Solar Domestic Water Heating Energy Contribution in tonnes/year | 55.1% | 28 |
| `ERSSPACECOOLENERGY` | Annual Energy Consumption for Space Cooling in MJ (Base Case – Standard Operating Conditions) | 55.1% | >20000 |
| `ERSVENTILATIONENERGY` | Rated Annual Ventilation Energy Consumption in MJ (Base Case - Standard Operating Conditions) | 55.1% | 19922 |
| `ERSWATERHEATINGENERGY` | Rated Domestic Hot Water Energy Consumption (MJ) | 55.1% | >20000 |
| `ERSWOODGHG` | Rated Wood Green House Gas Emissions (tonnes/year) | 55.1% | 202 |
| `ESTAR` | For v10 files: Indicates the ENERGY STAR New Homes compliance path (ESTARperf or ESTARcchtPres) For v11 files: Indicates the ENERGY STAR New Homes performance path ("Performance") or non-ESNH house (“EGH”) | 96.9% | 6 |
| `EUGRAIRTIGHTNESSPRIORITY` | The order that the airtightness upgrade has been prioritized by the energy advisor. | 19.3% | 39 |
| `EUGRCATHEDRALCEILFLATPRIORITY` | The order that the cathedral ceiling upgrade has been prioritized by the energy advisor. | 19.2% | 26 |
| `EUGRCEILINGSPRIORITY` | The order that the ceiling upgrade has been prioritized by the energy advisor. | 19.3% | 37 |
| `EUGRCOOLINGPRIORITY` | The order that the cooling upgrade has been prioritized by the energy advisor. | 19.3% | 33 |
| `EUGRDOORSPRIORITY` | The order that the door upgrade has been prioritized by the energy advisor. | 19.2% | 36 |
| `EUGRFLOORPRIORITY` | The order that the exposed floor upgrade has been prioritized by the energy advisor. | 19.1% | 22 |
| `EUGRFOUNDATIONPRIORITY` | The order that the foundation upgrade has been prioritized by the energy advisor. | 19.3% | 33 |
| `EUGRHEATINGPRIORITY` | The order that the heating upgrade has been prioritized by the energy advisor. | 19.3% | 40 |
| `EUGRHOTWATERPRIORITY` | The order that the water heater upgrade has been prioritized by the energy advisor. | 19.3% | 42 |
| `EUGRMAINWALLSPRIORITY` | The order that the main walls upgrade has been prioritized by the energy advisor. | 19.2% | 29 |
| `EUGRVENTILATIONPRIORITY` | The order that the ventilation upgrade has been prioritized by the energy advisor. | 19.2% | 38 |
| `EUGRWINDOWSPRIORITY` | The order that the window upgrade has been prioritized by the energy advisor. | 0.0% | 0 |
| `EVALTYPE` | Type of Evaluation, D, E, P or N | 100.0% | 4 |
| `EVALUATIONSID` | Identifier representing a unique Pre and post-retrofit evaluation pair (i.e. D and E files for the same house will have the same EvaluationsId) | 100.0% | >20000 |
| `EVCharger` | Indicates the ENERGY STAR number of the electric vehicle charging unit | 7.2% | 24 |
| `EXPOSEDFLOOR` | For v10 files: Description of exposed floor insulation (displays area of exposed floor in square feet, followed by the nominal R-value) For v11 files: Description of exposed floor insulation (displays percentage of floor area, followed by the nominal R-value) | 35.7% | >20000 |
| `EXPOSEDFLOORDEF` | Description of exposed floor insulation (displays area of exposed floor in square feet, followed by the nominal R-value) | 16.6% | >20000 |
| `FIREPLACEDAMP1` | Fireplace (solid fuel burning equipment) #1 Damper position (0=closed, 1= Open, 2=N/A) | 99.9% | 3 |
| `FIREPLACEDAMP2` | Fireplace (solid fuel burning equipment) #2 Damper position (0=closed, 1= Open, 2=N/A) | 99.9% | 3 |
| `FLOORAREA` | Floor area of the house, calculated using the volume divided by 2.5 (square metres) | 100.0% | 11177 |
| `FNDDEF` | Description of foundation insulation (displays percentage of foundation area, followed by the nominal R-value) | 90.3% | >20000 |
| `FNDHDR` | Foundation header insulation (percentage of header area, followed by the nominal R-value) For v10 files: Basement header only, crawl space headers were modeled as part of crawl space walls For v11.3-11.12 files: Basement and crawl space header For v11.13 files: Basement header only, crawl space headers are reported under the CSHDR field | 85.0% | >20000 |
| `FNDTYPE` | Type of foundation (B = Basement wall, P= Pony wall, C = crawl space, S = slab on grade, F = Floor above crawl space) | 90.3% | 323 |
| `FNDWALLINS` | Foundation effective insulation RSI value | 100.0% | 1697 |
| `FOOTPRINT` | Sum of the areas of all foundations and exposed floors (square metres) | 100.0% | 4837 |
| `FURDCMOTOR` | Heating system Fan/Pump Energy Efficient motor (1 = Yes, 0 = No) | 94.2% | 4 |
| `FURNACEFUEL` | Primary heating equipment fuel type | 100.0% | 9 |
| `FURNACEMODEL` | Furnace model | 62.3% | >20000 |
| `FURNACETYPE` | Primary heating equipment type | 100.0% | 58 |
| `FURSSEFF` | Primary heating equipment efficiency (Steady State efficiency) | 100.0% | 309 |
| `GHGI` | Used to specify the Greenhouse gas intensity - represents the operational greenhouse gas emissions of the proposed house normalized by floor area  (tons/square metres) | 25.0% | 11551 |
| `GUARDED` | A true or false value indicating whether the blower door test was guarded or unguarded | 25.2% | 4 |
| `HEATAFUE` | Primary heating equipment AFUE value | 94.2% | 274 |
| `HEATEDFLOORAREA` | Heated Floor Area (square metres) | 55.1% | >20000 |
| `HEATSYSSIZEOP` | Heating system sizing option (1 = calculated, 2 = User specified) | 99.9% | 3 |
| `HOUSEID` | Identifier unique to an address. All evaluations with the same address information (ClientAddr, ClientCity, HouseRegion, and ClientPCode) will have the same HouseID | 100.0% | >20000 |
| `HOUSEREGION` | Region of country where the house is located (province/territory) | 100.0% | 205 |
| `HPCAP` | Heat pump capacity (Watts) | 87.6% | >20000 |
| `HPEquipType` | Indicates the type of heat pump (Central split System, Central single package system, Ductless Mini- or Multi-split system, Compact Ducted Mini- or Multi-split system, and Coils Only) | 7.2% | 8 |
| `HPESTAR` | Air source heat pump is ENERGY STAR (ESTAR or N/A) | 7.8% | 2 |
| `HPSOURCE` | Heat pump type (air, water, ground or N/A) | 100.0% | 5 |
| `HRVEFF0C` | HRV effectiveness at 0 °C (%) | 100.0% | 312 |
| `HSEVOL` | House volume (cubic metres) | 100.0% | >20000 |
| `HVIEQUIP` | HRV/ERV is Home Ventilating Institute (HVI) certified (HVI or N/A) | 6.6% | 1 |
| `INDFURNACEFUEL` | Fuel used by largest independent heating system (only available for MURB files prior to v11) | 54.3% | 6 |
| `INDFURNACETYPE` | Type of largest independent heating system (only available for MURB files prior to v11) | 54.3% | 5 |
| `INDFURSSEFF` | Steady state efficiency of independent heating system that has the largest capacity (only available for MURB files prior to v11) | 99.9% | 121 |
| `INSCOPEOFNBC` | A true or false value indicating whether the proposed house is within the scope of the NBC Section 9.36 | 18.6% | 1 |
| `KWPV` | Contains the nominal capacity of the PV system (in kW) entered by the energy advisor | 36.8% | 2579 |
| `LARGESTCSIA` | CSIA rating of the largest solar domestic hot water system in the file | 76.4% | 358 |
| `LEAKAR` | Equivalent leakage area at 10 pascals | 100.0% | >20000 |
| `LFTOILETS` | Number of low-flow toilets | 94.2% | 48 |
| `MAINWALLINS` | Main walls effective insulation RSI value | 100.0% | 985 |
| `MEUI` | Mechanical Energy Use Intensity (kWh/(m2*year)) | 18.6% | >20000 |
| `MINR10EXPFLOOR` | Indicates a minimum of R10 continuous exposed floor insulation in northern communities (1 = yes, 0 = no) | 36.7% | 4 |
| `MOISTUREPROOFCS` | Indicates crawl space moisture proofing (1 = yes, 0 = no) | 36.7% | 4 |
| `MURBASHPESTAR` | Number of ENERGY STAR qualified air-source heat pumps in a MURB | 92.2% | 25 |
| `MURBDHWCOND` | Number of condensing domestic hot water tanks in a MURB | 92.2% | 40 |
| `MURBDHWCONDINSES` | Number of ENERGY STAR instantaneous (condensing) domestic hot water in the units | 87.6% | 16 |
| `MURBDHWINS` | Number of instantaneous domestic hot water tanks in a MURB | 92.2% | 16 |
| `MURBDHWINSES` | Number of ENERGY STAR instantaneous domestic hot water tanks in the units | 87.6% | 9 |
| `MURBDWHRL1M` | Number of Drain water heat recovery coils with efficiency between 30 to 42 % in MURB | 92.2% | 7 |
| `MURBDWHRM1M` | Number of Drain water heat recovery coils with efficiency between 43 and 54 % in MURB | 92.2% | 9 |
| `MURBFURDCMOTOR` | Up to three values in v.10.51, and up to two types in v.11 (type1; type2; type3) of heating system Fan/Pump, Energy Efficient motor (1=Yes, 0=No) | 2.0% | 15 |
| `MURBFURNACEFUEL` | Up to three types in v.10.51, and up to two types in v.11 (type1; type2; type3) of heating system fuel | 2.0% | 33 |
| `MURBFURNACETYPE` | Up to three types in v.10.51, and up to two types in v.11 (type1; type2; type3) of heating system | 2.0% | 227 |
| `MURBFURSSEFF` | Up to three types in v.10.51, and up to two types in v.11 (type1; type2; type3) of heating system steady state efficiency | 2.0% | 558 |
| `MURBHEATAFUE` | Up to three types in v.10.51, and up to two types in v.11 (type1; type2; type3) of heating system AFUE | 2.0% | 545 |
| `MURBHRVHVI` | Number of HVI heat recovery ventilators in MURB | 92.2% | 40 |
| `MURBHSESTAR` | Number of ENERGY STAR heating systems in MURB | 92.2% | 16 |
| `MURBHTSYSTEMDIS` | MURB central distribution system (All units central, all independent, combo) (only available for files prior to v11) | 54.4% | 5 |
| `MURBSOCMULTIPLIER` | Contains number of units, used to determine the SOC values of the building (one unit = 1, whole building = UnitsMURB value) | 48.2% | 65 |
| `MURBWOODEPA` | Number of EPA/CSA heating systems in MURB | 92.2% | 6 |
| `MURBWOODHEAT` | Number of wood appliances present in the MURB units | 92.2% | 18 |
| `NBCANNUALENEGYCONSUMPTION` | The energy consumption of the proposed house minus the electrical base loads stated in gigajoules | 18.9% | >20000 |
| `NBCHOUSEENERGYTARGET` | The energy consumption of the reference house minus the electrical base loads stated in gigajoules | 18.6% | 18187 |
| `NELECTHERMOS` | Number of Electronic Thermostats (0,1,2,3...) | 94.2% | 113 |
| `NLA` | Normalized Leakage Area (NLA is calculated by dividing the Equivalent Leakage Area at 10 Pa by the area of the exterior building envelope) | 100.0% | 2142 |
| `NLR` | Normalized Leakage Rate (calculated by multiplying the AIR50P value by the house volume, divided by the entire surface area) | 31.4% | 8671 |
| `NONRESHEATEDFLOORAREA` | Contains the heated floor area of non-residential units (square metres) | 48.2% | 657 |
| `NUMBEROFHEADS` | Displays the number of heads or warm air registers for mini-split air-source heat pumps | 36.8% | 41 |
| `NUMBUILDINGSTOREYS` | Displays the number of floors above grade (only active when Buildingtype = Multi-unit: one unit) | 48.2% | 8 |
| `NUMDOORESTAR` | Number of installed ENERGY STAR certified doors | 94.2% | 37 |
| `NUMDOORS` | Total number of installed doors | 94.2% | 71 |
| `NUMDWELLINGUNITS` | Contains the number of residential units in a MURB | 48.2% | 70 |
| `NUMER34TO39` | The number of windows meeting the  ER ≥ 34 &lt;40 characteristic | 36.8% | 132 |
| `NUMER40PLUS` | The number of windows meeting ER ≥ 40 | 36.8% | 91 |
| `NUMHPWHMURB` | Used to indicate the number of heat pump water heaters installed in a MURB | 36.8% | 9 |
| `NUMNONRESUNITS` | Contains the number of non-residential units in a MURB | 48.2% | 15 |
| `NUMSOLSYS` | The total number of solar domestic hot water systems in the file | 76.4% | 5 |
| `NUMWINDOWS` | Total number of installed windows | 94.2% | 278 |
| `NUMWINESTAR` | Number of installed ENERGY STAR certified windows | 94.2% | 176 |
| `NUMWINU105` | The number of windows with a U value  ≤ 1.05 | 36.8% | 95 |
| `NUMWINU122` | The number of windows with a U value of &gt;1.05 and  ≤ 1.22 | 36.8% | 91 |
| `OVERALLIMPROVEMENT` | For the purpose of compliance to the National Building Code Energy Performance Tiers, this value represents the energy performance improvement of the proposed house over that of the reference house.  For v11.10- v11.12 files: Base loads and PV are excluded, solar hot water heating is included For v11.13 files: Base loads and all renewables are excluded. | 18.6% | >20000 |
| `PDHWEF` | Primary domestic hot water equipment efficiency | 100.0% | 2339 |
| `PDHWESTAR` | Primary domestic hot water is ENERGY STAR certified (ecoLIST when ecoEnergy, ESTARecoLIST when both are checked, or N/A) | 6.0% | 5 |
| `PDHWFUEL` | Primary domestic hot water equipment fuel type | 100.0% | 12 |
| `PDHWTYPE` | Primary domestic hot water equipment type | 100.0% | 33 |
| `PDHWUEF` | Primary domestic hot water UEF | 100.0% | 100 |
| `PDRAWPATTERN` | Draw pattern for primary domestic hot water system | 1.3% | 6 |
| `PEAKCOOLINGVALIDATION` | A true or false value indicating whether the proposed house design cooling load is equal to or lower than the reference house design cooling load | 18.6% | 2 |
| `PONYWALLEXISTS` | Presence of pony walls (0 = No, 1 = Yes) | 99.9% | 4 |
| `PRIDHWMODEL` | Primary Domestic Hot Water equipment model | 36.5% | >20000 |
| `PRIMARYDHWTANKVOLUME` | Displays the domestic hot water tank volume for the primary system (litres) | 36.8% | 3051 |
| `PROGRAMNAME` | Indicates which version of HOT2000 was used (e.g. HOT2000 v.9.34c, HOT2000 v.10.51, HOT2000 v.11.6) | 100.0% | 67 |
| `PROGSMARTTHERMOSTAT` | Indicates the presence of programmable, smart or adaptive thermostats (1 = yes, 0 = no) | 36.7% | 4 |
| `PROVINCE` | Two character Province Code for House region | 100.0% | 13 |
| `QTOT` | Rated total combined natural and mechanical ventilation in L/s | 55.1% | >20000 |
| `QWARN` | Calculated total combined natural and mechanical ventilation value in L/s for which the insufficient ventilation warning appears in reports (16 L/s ≤ Qwarn ≤ 40L/s) | 55.1% | 2453 |
| `ROOFINGMEMBRANE` | Indicates adhesive waterproof ice and water barrier underlayment for roofs (1 = yes, 0 = no) | 36.7% | 4 |
| `RULESETTYPE` | Mode selected within HOT2000 (EnerGuide Rating System (2015 NBC), Ontario Reference House, EnerGuide Rating System 2020 NBC) | 47.4% | 5 |
| `SDHWEF` | Secondary domestic hot water efficiency | 93.9% | 829 |
| `SDHWESTAR` | Equal to "ESTAR" if the secondary domestic hot water tank is ENERGY STAR certified, "N/A" otherwise | 0.1% | 4 |
| `SDHWFUEL` | Secondary domestic hot water fuel | 93.9% | 10 |
| `SDHWHPCOP` | Secondary domestic hot water heat-pump coefficient of performance | 93.9% | 38 |
| `SDHWHPTYPE` | Secondary domestic hot water heat-pump type | 0.0% | 14 |
| `SDHWTYPE` | Secondary domestic hot water type | 93.9% | 25 |
| `SDHWUEF` | Secondary domestic hot water UEF | 100.0% | 50 |
| `SDRAWPATTERN` | Draw pattern for secondary domestic hot water system | 0.1% | 6 |
| `SECONDARYDHWTANKVOLUME` | Displays the domestic hot water tank volume for the secondary system (litres) | 36.8% | 842 |
| `SLABFLOORAREA` | Slab floor area (square metres) | 100.0% | >20000 |
| `SLABINSUL` | Indicates basement slab insulation (1 = yes, 0 = no) | 36.7% | 4 |
| `STOREYS` | Number of floors above grade (if buildingtype = Multi-unit: one unit assessed, this field refers to the number of floors above grade for the unit) | 100.0% | 9 |
| `SUPPHTGFUEL1` | Supplementary heating system #1 Fuel | 48.8% | 9 |
| `SUPPHTGFUEL2` | Supplementary heating system #2 Fuel | 11.3% | 9 |
| `SUPPHTGTYPE1` | Supplementary heating system #1 Type | 48.8% | 56 |
| `SUPPHTGTYPE2` | Supplementary heating system #2 Type | 11.3% | 33 |
| `TBSMNT` | Temperature of the basement in Celsius | 100.0% | 95 |
| `TEDI` | Thermal Energy Demand Intensity stated in kWh/(m2*year) | 18.6% | >20000 |
| `TMAIN` | Temperature of the main floor in Celsius | 100.0% | 77 |
| `TOTALOCCUPANTS` | Total number of occupants based on Standard Operating Conditions | 100.0% | 59 |
| `TOTALVENTEXH` | Total ventilation exhaust rate, L/s | 99.9% | 5103 |
| `TOTALVENTSUPPLY` | Total ventilation supply rate, L/s | 99.9% | 3717 |
| `TOTCSIA` | Sum of the CSIA ratings for solar domestic hot water systems in the file | 76.4% | 358 |
| `TYPE1CAPACITY` | Capacity of the Type 1 (i.e. baseboards, boiler, combo and furnace) heating system (Watts) | 87.6% | 9006 |
| `TYPEOFHOUSE` | Type of house (e.g. Single Detached, Double/Semi-detached, Row house- end unit, Row house- middle unit, etc.) | 100.0% | 23 |
| `UATTCEILINGDEF` | Description of proposed attic insulation (displays percentage of attic area, followed by the nominal R-value) | 89.6% | >20000 |
| `UCAFLCEILINGDEF` | Description of proposed cathedral or flat roof insulation (displays percentage of ceiling area, followed by nominal R-value) | 23.8% | >20000 |
| `UCENVENTSYSTYPE` | Proposed ventilation system type | 28.8% | 4 |
| `UDWHRL1M` | Proposed number of Drain-water heat recovery smaller than 1 meter | 94.2% | 6 |
| `UDWHRM1M` | Proposed number of Drain-water heat recovery greater than 1 meter | 94.2% | 7 |
| `UEPACSASUPPHTG1` | Proposed Supplementary Heating system 1 (solid fuel burning) meets CSA or EPA standard | 3.2% | 1 |
| `UEPACSASUPPHTG2` | Proposed Supplementary Heating system 2 (soild fuel burning) meets CSA or EPA standard | 0.6% | 1 |
| `UGEXPOSEDFLOOR` | Description of proposed exposed floor insulation (displays percentage of floor area, followed by the nominal R-value) | 35.7% | >20000 |
| `UGRACCENTESTAR` | Proposed central A/C is ENERGY STAR (ESTAR or N/A) | 37.6% | 1 |
| `UGRACWINDESTAR` | Proposed number of window A/C unit that are ENERGY STAR certified (0,1,2,3,4…) | 94.2% | 16 |
| `UGRACWINDNUM` | Proposed number of window A/C unit (installed and recommended) | 94.2% | 19 |
| `UGRAIR50PA` | Proposed air change per hour target at 50 Pa | 100.0% | >20000 |
| `UGRAIRCONDTYPE` | Proposed type of A/C System (Central split System, Central single package system, Ductless Mini- or Multi-split system, Compact Ducted Mini- or Multi-split system, and Coils Only) or “Not installed” | 94.0% | 13 |
| `UGRAIRCOP` | Proposed coefficient of performance for A/C system | 94.2% | 2731 |
| `UGRASHPHSPF` | Indicates the heating efficiency of a proposed Air Source Heat Pump (HSPF value or 0) | 7.2% | 653 |
| `UGRASHPHSPF2` | Indicates the heating efficiency of a proposed Air Source Heat Pump (HSPF2 value or 0) | 7.2% | 390 |
| `UGRBATTERYSTORAGE` | Proposed battery storage installation/replacement (1 = yes, 0 = no) | 36.7% | 4 |
| `UGRCCASHP` | Proposed cold climate air-source heat pump (1 = yes, 0 = no) | 36.7% | 4 |
| `UGRCEILINGTYPE` | Proposed ceiling type (‘A’ for a gable/hip/scissor attic, or ‘F’ for a flat or cathedral attic) | 94.0% | 152 |
| `UGRCEILINS` | Proposed ceiling effective insulation RSI value | 100.0% | 1766 |
| `UGRCREDITPV` | — | 99.9% | >20000 |
| `UGRCREDITWIND` | — | 99.9% | 66 |
| `UGRCRITNATACH` | Proposed critical natural air change per hour | 100.0% | 15383 |
| `UGRCRITTOTACH` | Proposed total critical air change per hour | 100.0% | >20000 |
| `UGRCSHDR` | Proposed crawl space header insulation (percentage of header area, followed by the nominal R-value) | 0.6% | 3504 |
| `UGRDESHTLOSS` | Proposed design heat loss in Watts | 100.0% | >20000 |
| `UGRDHWCSIA` | Proposed Canadian Solar Industry Association rating for solar Domestic Hot water system (MJ/y) | 100.0% | 459 |
| `UGRDHWHPCOP` | Proposed domestic hot water heat pump system coefficient of performance | 100.0% | 179 |
| `UGRDHWHPTYPE` | Proposed domestic hot water heat pump system type | 6.1% | 3 |
| `UGRDHWSYSEF` | Proposed domestic hot water equipment efficiency (EF) | 100.0% | 950 |
| `UGRDHWSYSFUEL` | Proposed domestic hot water equipment fuel type | 64.3% | 12 |
| `UGRDHWSYSTYPE` | Proposed domestic hot water equipment type | 64.3% | 37 |
| `UGREIDEF` | Description of proposed exterior foundation wall insulation (displays percentage of foundation exterior wall area, followed by the nominal R-value) | 41.1% | 10509 |
| `UGREPACSA` | Proposed Wood Fireplace or insert meets EPA or CSA  standards, else equal N/A | 0.1% | 1 |
| `UGRERSENERGYINTENSITY` | Proposed Rated Energy Intensity (Proposed EnerGuide Rating divided by the heated floor area) (GJ/square metres) | 55.1% | 503 |
| `UGRERSGHG` | Proposed Total Annual Green House Gas Emissions in tonnes/year | 55.1% | 590 |
| `UGRERSHLDOOR` | Proposed Heat loss through doors in GJ/year | 55.1% | >20000 |
| `UGRERSHLWINDOW` | Proposed Heat loss through windows in GJ/year | 55.1% | >20000 |
| `UGRERSLIGHTAPPLIANCEENERGY` | Proposed Rated Annual Energy Consumption for Lights and Appliances in MJ based on Standard Operating Conditions | 55.1% | 4174 |
| `UGRERSOTHERELECENERGY` | Proposed Rated Annual Energy Consumption for Other Electrical in MJ based on Standard Operating Conditions | 55.1% | 54 |
| `UGRERSRATING` | Proposed EnerGuide Rating in GJ/year | 55.1% | 1500 |
| `UGRERSSPACECOOLENERGY` | Proposed Annual Energy Consumption for Space Cooling in MJ based on Standard Operating Conditions | 55.1% | >20000 |
| `UGRERSVENTILATIONENERGY` | Proposed Rated Ventilation Energy Consumption in MJ | 55.1% | >20000 |
| `UGRERSWATERHEATINGENERGY` | Proposed Rated Domestic Hot Water Energy Consumption in MJ based on Standard Operating Conditions | 55.1% | >20000 |
| `UGREVCharger` | Indicates that an electric vehicle charging unit has been proposed (1 = yes, 0 = no) | 7.2% | 2 |
| `UGREXPOSEDFLOORDEF` | Description of proposed exposed floor insulation (displays area of exposed floor, followed by the nominal R-value) | 14.9% | >20000 |
| `UGRFCONELEC` | Proposed consumption of electricity (kWh) | 100.0% | >20000 |
| `UGRFCONNGAS` | Proposed consumption of natural gas (cubic metres) | 100.0% | >20000 |
| `UGRFCONOIL` | Proposed consumption of oil (litres) | 100.0% | >20000 |
| `UGRFCONPROP` | Proposed consumption of propane (litres) | 100.0% | >20000 |
| `UGRFCONTOTAL` | Proposed total energy consumption (MJ) | 100.0% | >20000 |
| `UGRFCONWOOD` | Proposed consumption of wood (tonne) | 100.0% | >20000 |
| `UGRFNDDEF` | Description of proposed foundation insulation (displays percentage of foundation area, followed by the nominal R-value) | 90.3% | >20000 |
| `UGRFNDHDR` | Proposed foundation header insulation (percentage of header area, followed by the nominal R-value) For v10 files: Basement header only, crawl space headers were modeled as part of crawl space walls For v11.3-11.12 files: Basement and crawl space header For v11.13 files: Basement header only, crawl space headers are reported under the CSHDR field | 85.0% | >20000 |
| `UGRFNDINS` | Proposed foundation effective insulation RSI value | 100.0% | 1781 |
| `UGRFNDTYPE` | Proposed type of foundation (B = Basement wall, P = Pony wall, C = crawl space, S = slab on grade, F = Floor above crawl space) | 90.3% | 326 |
| `UGRFURDCMOTOR` | Proposed heating system fan/pump energy efficient motor 1=Yes, 0=No | 94.2% | 4 |
| `UGRFURNACEAEC` | Proposed annual energy consumption for the Type 1 heating system in MJ | 100.0% | >20000 |
| `UGRFURNACEEFF` | Proposed primary heating equipment efficiency (steady state) | 100.0% | 307 |
| `UGRFURNACEFUEL` | Proposed primary heating equipment fuel type | 100.0% | 9 |
| `UGRFURNACETYP` | Proposed primary heating equipment type | 100.0% | 56 |
| `UGRFURSEASEFF` | Proposed heating system Seasonal Efficiency | 100.0% | 4238 |
| `UGRHEATAFUE` | Proposed primary heating equipment AFUE value | 94.2% | 249 |
| `UGRHEATFCONSE` | Heating energy consumption - Upgrade case Electric (kWh) | 94.2% | >20000 |
| `UGRHEATFCONSG` | Heating energy consumption - Upgrade case Natural Gas (cubic metres) | 94.2% | >20000 |
| `UGRHEATFCONSO` | Heating energy consumption - Upgrade case Oil (litres) | 94.2% | >20000 |
| `UGRHEATFCONSP` | Heating energy consumption - Upgrade case Propane (litres) | 94.2% | >20000 |
| `UGRHEATFCONSW` | Heating energy consumption - Upgrade case Wood (tonne) | 94.2% | >20000 |
| `UGRHLAIR` | Upgrade case: heat loss to air leakage (MJ) | 100.0% | >20000 |
| `UGRHLCEILING` | Upgrade case: heat loss to ceiling (MJ) | 100.0% | >20000 |
| `UGRHLEXPOSEDFLR` | Upgrade case: heat loss to exposed floor (MJ) | 100.0% | >20000 |
| `UGRHLFOUND` | Upgrade case: heat loss to foundation (MJ) | 100.0% | >20000 |
| `UGRHLWALLS` | Upgrade case: heat loss to wall (MJ) | 100.0% | >20000 |
| `UGRHLWINDOOR` | Upgrade case: heat loss to windows and doors (MJ) | 100.0% | >20000 |
| `UGRHPCOP` | Proposed heat pump coefficient of performance | 100.0% | 1600 |
| `UGRHPEquipType` | Indicates the proposed type of heat pump (Central split System, Central single package system, Ductless Mini- or Multi-split system, Compact Ducted Mini- or Multi-split system, and Coils Only) | 7.2% | 8 |
| `UGRHPESTAR` | Proposed Air Source HP is ENERGY STAR (ESTAR, or N/A) | 29.0% | 2 |
| `UGRHPTYPE` | Proposed heat pump type (air, water, ground, or N/A) | 100.0% | 5 |
| `UGRHVIEQUIP` | Proposed HRV/ERV is Home Ventilating Institute (HVI) certified (HVI or N/A) | 24.3% | 1 |
| `UGRINDFURNACEFU` | Upgrade case: Fuel used by largest independent heating system (only available for MURB files prior to v11) | 54.3% | 7 |
| `UGRINDFURNACETP` | Proposed type of largest independent heating system (only available for MURB files prior to v11) | 54.3% | 7 |
| `UGRINDFURSSEFF` | Proposed steady state efficiency of largest independent heating system (only available for MURB files prior to v11) | 99.9% | 122 |
| `UGRINEXPOSEDFLR` | Proposed exposed floor effective insulation RSI value | 100.0% | 1388 |
| `UGRKWPV` | Contains the capacity of the proposed PV system (in kW DC) | 36.8% | 1212 |
| `UGRMINR10EXPFLOOR` | Proposed installation of a minimum of R10 continuous exposed floor insulation in northern communities (1 = yes, 0 = no) | 36.7% | 4 |
| `UGRMOISTUREPROOFCS` | Proposed crawl space moisture proofing (1 = yes, 0 = no) | 36.7% | 4 |
| `UGRNELECTHERMOS` | Proposed Number of Electronic Thermostats (0,1,2,3...) | 94.2% | 121 |
| `UGRNUMBEROFHEADS` | Displays the proposed number of heads or warm air registers for mini-split air-source heat pumps | 36.8% | 42 |
| `UGRNUMDOORESTAR` | Proposed number of ENERGY STAR certified doors (installed and recommended) | 94.2% | 56 |
| `UGRNUMER34TO39` | Proposed number of windows meeting ER ≥ 34 and &lt; 40 | 36.8% | 171 |
| `UGRNUMER40PLUS` | Proposed number of windows meeting ER ≥ 40 | 36.8% | 102 |
| `UGRNUMWINESTAR` | Proposed number of ENERGY STAR certified windows (installed + recommended) | 94.2% | 239 |
| `UGRNUMWINU105` | Proposed number of windows with a U value ≤ 1.05 | 36.8% | 166 |
| `UGRNUMWINU122` | Proposed number of windows with a U value &gt; 1.05 and  ≤ 1.22 | 36.8% | 177 |
| `UGRPDHWESTAR` | Proposed primary domestic hot water is ENERGY STAR certified (ESTAR, or N/A) | 25.2% | 4 |
| `UGRPDHWUEF` | Proposed primary domestic hot water efficiency (in UEF) | 100.0% | 142 |
| `UGRPDRAWPATTERN` | Draw pattern for proposed primary domestic hot water | 1.0% | 31 |
| `UGRPROGSMARTTHERMOSTAT` | Proposed programmable, smart or adaptive thermostats (1 = yes, 0 = no) | 36.7% | 4 |
| `UGRRATING` | Proposed EnerGuide rating for 0-100 scale  (only available for files prior to v11) | 100.0% | 535 |
| `UGRROOFINGMEMBRANE` | Proposed adhesive waterproof ice and water barrier underlayment for roofs (1 = yes, 0 = no) | 36.7% | 4 |
| `UGRSDHWESTAR` | Proposed secondary domestic hot water is ENERGY STAR certified (ESTAR, or N/A) | 0.3% | 5 |
| `UGRSDHWHPCOP` | Proposed secondary domestic hot water heat-pump coefficient of performance | 93.9% | 41 |
| `UGRSDHWHPTYPE` | Proposed secondary domestic hot water heat-pump type | 0.2% | 20 |
| `UGRSDHWSYSEF` | Proposed secondary domestic hot water efficiency (EF) | 93.9% | 454 |
| `UGRSDHWSYSFUEL` | Proposed secondary domestic hot water fuel | 93.9% | 11 |
| `UGRSDHWSYSTYPE` | Proposed secondary domestic hot water type | 93.9% | 24 |
| `UGRSDHWUEF` | Proposed secondary domestic hot water efficiency (UEF) | 100.0% | 35 |
| `UGRSDRAWPATTERN` | Proposed draw pattern for secondary domestic hot water | 0.0% | 154 |
| `UGRSLABINSUL` | Proposed basement slab insulation (1 = yes, 0 = no) | 36.7% | 7 |
| `UGRSPACEENERGY` | Proposed rated annual space heating energy consumption for and ventilator electrical consumption (during heating hour) (MJ) | 55.1% | >20000 |
| `UGRSUMPPUMP` | Proposed sump pump with alarm and battery backup (1 = yes, 0 = no) | 36.7% | 4 |
| `UGRSUPPHTGFUEL1` | Proposed supplementary heating system #1 Fuel | 48.5% | 9 |
| `UGRSUPPHTGFUEL2` | Proposed supplementary heating system #2 Fuel | 11.1% | 9 |
| `UGRSUPPHTGTYPE1` | Proposed supplementary heating system #1 Type | 48.5% | 58 |
| `UGRSUPPHTGTYPE2` | Proposed supplementary heating system #2 Type | 11.2% | 33 |
| `UGRTOTALVENTEXH` | Proposed total ventilation exhaust rate (L/s) | 99.9% | 6019 |
| `UGRTOTALVENTSUP` | Proposed total ventilation supply rate (L/s) | 99.9% | 3303 |
| `UGRWALLDEF` | Proposed description of wall insulation (displays percentage of wall area, followed by the nominal R-value) | 94.0% | >20000 |
| `UGRWALLINS` | Proposed wall effective insulation RSI value | 100.0% | 1008 |
| `UGRWATERPROOF` | Proposed waterproofing for basements (1 = yes, 0 = no) | 36.7% | 4 |
| `UGRWINDOWCODE` | Window code of the proposed windows that occupy the greatest area. Ignores user defined codes. | 87.4% | 7609 |
| `ULFTOILETS` | Proposed number of low-flow toilets | 94.2% | 65 |
| `UMURBDHWCONDINES` | Number of ENERGY STAR certified instantaneous (condensing) domestic hot water tanks in the MURB units in the upgrade case | 87.6% | 9 |
| `UMURBDHWINSES` | Number of ENERGY STAR instantaneous domestic hot water tanks in the units in the upgrade case | 87.6% | 10 |
| `UNITSCONNECTEDDWHR` | Number of Multi-Unit Residential Building (MURB) units connected to a drain water heat recovery system | 100.0% | 8 |
| `UNITSMURBS` | — | 99.9% | 68 |
| `UWINDOWCODENUM` | Proposed window code used most often in the file. Ignores user defined codes. | 64.6% | 6571 |
| `VISITEDUNITS` | Number of MURB units visited during evaluation | 99.9% | 70 |
| `WALKOUTFLOORAR` | Walkout floor area in square metres | 99.9% | 3085 |
| `WALLDEF` | Description of wall insulation (displays percentage of wall area, followed by the nominal R-value) | 94.0% | >20000 |
| `WATERPROOF` | Proposed basement waterproofing (1 = yes, 0 = no) | 36.7% | 4 |
| `WEATHERLOC` | Climate data location | 100.0% | 424 |
| `WINDOWCODE` | Window code of the windows that occupy the greatest area. Ignores user defined codes. | 88.4% | 6735 |
| `WINDOWCODENUM` | Window code used most often in the file. Ignores user defined codes. | 65.1% | 5670 |
| `WTHDATA` | Climate data file | 93.9% | 6 |
| `YEARBUILT` | Year of construction | 100.0% | 321 |
| `CoolingSeasonMonths` | Number of cooling months | 44.7% | 2 |
| `ERSDesCoolLoss` | Total design cooling load (Watts) | 44.7% | >20000 |
| `ERSPVAvailableEnergy` | Amount of Photovoltaic energy generated on site in kWh, uncapped | 44.7% | >20000 |
| `ERSTotalConsGHG` | GHG emissions from total energy consumption in tonnes/year | 44.7% | 706 |
| `ERSTotalRenewableGHG` | GHG emissions offset by total renewable energy in tonnes/year | 44.7% | 224 |
| `HotWaterTemperature` | Hot Water temperature in degrees C | 44.7% | 1 |
| `ROCApplianceLoad` | Reduced Operating Conditions Appliance load in kWh/day | 28.7% | 42 |
| `ROCHotWaterLoad` | Reduced Operating Conditions Total estimated hot water load in L/day | 28.7% | 232 |
| `ROCLightingLoad` | Reduced Operating Conditions Lighting load in kWh/day | 28.7% | 4 |
| `ROCOtherElectricalLoad` | Reduced Operating Conditions Other electrical load in kWh/day | 28.7% | 4 |
| `SOCApplianceLoad` | Standard Operating Conditions Appliance load in kWh/day | 44.7% | 37 |
| `SOCHotWaterLoad` | Standard Operating Conditions Total estimated hot water load in L/day | 44.7% | 1724 |
| `SOCLightingLoad` | Standard Operating Conditions Lighting load in kWh/day | 44.7% | 37 |
| `SOCOtherElectricalLoad` | Standard Operating Conditions Other electrical load in kWh/day | 44.7% | 37 |
| `ThermostatCooling` | Cooling temperature in degrees C based on standard operating conditions | 44.7% | 1 |
| `ThermostatHeatingNighttime` | Heating nighttime temperature in degrees C | 44.7% | 1 |
| `UGRAirTightnessERSRating` | Proposed ERS rating for airtightness upgrade recommendation (GJ) | 37.9% | 1089 |
| `UGRCeilingCathFlatERSRating` | Proposed ERS rating for cathedral or falt ceiling upgrade recommendation (GJ) | 29.5% | 874 |
| `UGRCeilingsERSRating` | Proposed ERS rating for attic ceiling upgrade recommendation (GJ) | 35.0% | 882 |
| `UGRCoolingERSRating` | Proposed ERS rating for space cooling system upgrade recommendation (GJ) | 33.1% | 868 |
| `UGRDoorsERSRating` | Proposed ERS rating for door upgrade recommendation (GJ) | 32.7% | 1057 |
| `UGRERSPVAvailableEnergy` | Proposed amount of photovoltaic energy generated on site in kWh, uncapped | 44.7% | >20000 |
| `UGRERSRenewableElec` | Proposed total annual renewable energy produced by photovoltaic systems and wind turbines (MJ), uncapped | 44.7% | >20000 |
| `UGRERSRenewableProd` | Proposed total available renewable energy production (electricity generation and solar DHW contribution) in MJ, capped at total annual energy consumption | 44.7% | >20000 |
| `UGRERSRenewableSolar` | Proposed renewable solar DHW contribution in MJ, uncapped | 44.7% | 817 |
| `UGRExposedFloorERSRating` | Proposed ERS rating for exposed floor upgrade recommendation (GJ) | 29.2% | 710 |
| `UGRFoundationERSRating` | Proposed ERS rating for foundation upgrade recommendation (GJ) | 33.4% | 1001 |
| `UGRGenerationERSRating` | Proposed ERS rating for renewable energy generation upgrade recommendation (GJ) | 29.8% | 875 |
| `UGRHeatingERSRating` | Proposed ERS rating for space heating system upgrade recommendation (GJ) | 36.9% | 925 |
| `UGRHotWaterERSRating` | Proposed ERS rating for domestic hot water system upgrade recommendation (GJ) | 32.8% | 829 |
| `UGRVentilationERSRating` | Proposed ERS rating for ventilation upgrade recommendation (GJ) | 31.2% | 864 |
| `UGRWallsERSRating` | Proposed ERS rating for main wall upgrade recommendation (GJ) | 31.6% | 940 |
| `UGRWindowsERSRating` | Proposed ERS rating for window upgrade recommendation (GJ) | 34.2% | 1043 |
| `UtilizedSolarGains` | Utilized solar gains in MJ | 44.7% | >20000 |
| `RefHLAir` | Reference House heat loss to air leakage (MJ) | 19.5% | >20000 |
| `RefHLFound` | Reference House heat loss to foundations (MJ) | 19.5% | >20000 |
| `RefHLCeiling` | Reference House heat loss to ceilings (MJ) | 19.5% | >20000 |
| `RefHLWalls` | Reference House heat loss to walls (MJ) | 19.5% | >20000 |
| `RefHLWinDoor` | Reference House heat loss through windows and doors (MJ) | 19.5% | >20000 |
| `RefHLExposedFlr` | Reference House heat loss to exposed floors (MJ) | 19.5% | >20000 |
| `RefHLWindow` | Reference House heat loss to windows (MJ) | 19.5% | >20000 |
| `RefHLDoor` | Reference House heat loss to doors (MJ) | 19.5% | >20000 |
| `RefDesHtLoss` | Reference House design heating load (Watts) | 19.5% | >20000 |
| `RefDesCoolLoss` | Reference House total design cooling load (Watts) | 19.5% | >20000 |
| `RefSpaceEnergy` | Reference House rated annual space heating energy consumption for and ventilator electrical consumption (during heating hour) (MJ) | 19.5% | >20000 |
| `RefSpaceCoolEnergy` | Reference House annual energy consumption for space cooling in MJ | 19.5% | >20000 |
| `RefWaterHeatEnergy` | Reference House annual energy consumption for domestic hot water heating in MJ | 0.0% | 35 |
| `RefVentilationEnergy` | Reference House annual energy consumption for ventilation in MJ | 19.5% | 9355 |

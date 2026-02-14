<?php
header('Content-type: application/xspf+xml');

$count = 0;
$countOut = 0;
$countAd = 0;
$countSubAd = 0;
$drDate = date('m.d');







if (file_exists('all_clips_test_out.xspf')) {

	$xml = simplexml_load_file('all_clips_test_out.xspf');

	foreach ($xml->trackList->track as $track) {
	    $count++;
	}

	$numbers = range(1, $count);
	shuffle($numbers);
	$xml_out = clone $xml;


	//$_REQUEST['dr']
	foreach ($numbers as $number) {
		if ($countAd===4) {
			$countSubAd++;
			$xml_out->trackList->track[$countOut]->location = 'file:///home/user/ad/ad'.$countSubAd.'.mp4';
			if ($countSubAd === 3) {
				$countSubAd = 0;
			}
		} elseif ($countAd===5) {
			$countAd = 0;
			$xml_out->trackList->track[$countOut]->location = 'file:///home/user/ad/dr'.$drDate.'.mp4';
		} else {
			$xml_out->trackList->track[$countOut]->location = $xml->trackList->track[$number]->location;
		}

	    $countOut++;
	    $countAd++;
	}
	echo $xml_out->asXML();
} else {
    exit('Не удалось открыть файл all_clips_test_out.xspf.');
}
